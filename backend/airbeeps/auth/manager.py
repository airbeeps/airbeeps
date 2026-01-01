import logging
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Union

from fastapi import Depends, HTTPException, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from sqlalchemy import func, select

from airbeeps.config import settings
from airbeeps.services.mail import MessageSchema, MessageType, get_sender
from airbeeps.users.models import User
from airbeeps.utils.language import detect_language

from .dependencies import get_user_db
from .oauth_models import OAuthProvider

if TYPE_CHECKING:
    from .api.v1.schemas import UserCreate

logger = logging.getLogger(__name__)


# Account lockout exception
class AccountLockedError(Exception):
    """Raised when an account is temporarily locked due to failed login attempts."""

    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        remaining = (locked_until - datetime.now(UTC)).total_seconds()
        self.remaining_seconds = max(0, int(remaining))
        super().__init__(f"Account locked for {self.remaining_seconds} seconds")


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    # Email sending rate limit (seconds)
    EMAIL_RATE_LIMIT_SECONDS = 60

    async def create(
        self,
        user_create: "UserCreate",
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """
        Override create to handle user creation
        """
        logger.info(f"Creating new user with email: {user_create.email}")

        # 1. Validate password
        await self.validate_password(user_create.password, user_create)

        # 2. Check existing user
        if user_create.email:
            existing_user = await self.user_db.get_by_email(user_create.email)
            if existing_user is not None:
                logger.warning(
                    f"Attempt to create user with existing email: {user_create.email}"
                )
                raise exceptions.UserAlreadyExists

        # 2.5 Bootstrap: the very first user becomes a superuser/admin.
        # This avoids shipping opinionated default admin credentials in seed data.
        is_first_user = False
        try:
            result = await self.user_db.session.execute(select(func.count(User.id)))
            user_count = int(result.scalar_one() or 0)
            is_first_user = user_count == 0
        except Exception:
            # If we cannot determine this safely, default to non-admin.
            logger.exception(
                "Failed to determine if this is the first user; defaulting to non-superuser"
            )
            is_first_user = False

        # 3. Prepare user dict
        user_dict = (
            user_create.create_update_dict()
            if safe
            else user_create.create_update_dict_superuser()
        )

        # 3.1 Server-side enforcement for admin bootstrap
        # The first user in a fresh install becomes an admin automatically.
        if safe:
            # Never allow clients to self-assign admin/superuser.
            user_dict["is_superuser"] = is_first_user
        else:
            # Preserve explicit admin creation, but still bootstrap the very first user.
            user_dict["is_superuser"] = (
                bool(user_dict.get("is_superuser", False)) or is_first_user
            )

        # 3.2 Server-side enforcement for public registration
        if safe:
            # If email is disabled, verification must not block logins.
            # When email is enabled, keep new users unverified until they click the link.
            user_dict["is_verified"] = not settings.MAIL_ENABLED

            # Always create active accounts via public registration.
            user_dict["is_active"] = True
        # For non-safe creation (admin/CLI flows), still respect MAIL_ENABLED defaulting.
        elif not settings.MAIL_ENABLED:
            user_dict["is_verified"] = True

        # 4. Handle password
        password = user_dict.pop("password")
        user_dict["hashed_password"] = self.password_helper.hash(password)

        # 5. Create user
        created_user = await self.user_db.create(user_dict)
        logger.info(
            f"Successfully created user {created_user.id} with email: {created_user.email}"
        )

        await self.on_after_register(created_user, request)

        return created_user

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        """
        Post-registration hook.

        - If email verification is enabled, automatically send a verification email.
        - If email is disabled, users are auto-verified at creation time (see create()).
        """
        if user.is_verified:
            return

        if not settings.MAIL_ENABLED:
            return

        if not user.email:
            logger.info(
                "User registered without email; skipping verification flow",
                extra={"user_id": str(user.id)},
            )
            return

        try:
            await self.request_verify(user, request)
        except Exception:
            # Don't fail registration if mail sending is misconfigured.
            logger.exception(
                "Failed to send verification email after registration",
                extra={"user_id": str(user.id), "email": user.email},
            )

    def _check_email_rate_limit(
        self, last_sent_at: datetime | None, email_type: str
    ) -> None:
        """
        Check email sending rate limit

        Args:
            last_sent_at: Last sent time
            email_type: Email type (for logging)

        Raises:
            HTTPException: If within rate limit time
        """
        if last_sent_at is None:
            return

        now = datetime.now(UTC)
        time_since_last_sent = now - last_sent_at

        if time_since_last_sent < timedelta(seconds=self.EMAIL_RATE_LIMIT_SECONDS):
            remaining_seconds = self.EMAIL_RATE_LIMIT_SECONDS - int(
                time_since_last_sent.total_seconds()
            )
            logger.warning(
                f"Rate limit hit for {email_type} email. "
                f"Last sent: {last_sent_at}, remaining: {remaining_seconds} seconds"
            )
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining_seconds} seconds before requesting another {email_type} email.",
            )

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        if not settings.MAIL_ENABLED:
            logger.info("MAIL_ENABLED is false; skipping verification email")
            return

        # Check rate limit
        self._check_email_rate_limit(
            user.last_verification_email_sent_at, "verification"
        )

        # Check if user has valid email
        if not user.email:
            logger.warning(
                f"Attempted to send verification email to user {user.id} but user has no email address"
            )
            return

        # Detect user language preference
        user_lang = detect_language(user.language, request)

        verify_link = (
            f"{str(settings.FRONTEND_URL).rstrip('/')}/verify-email?token={token}"
        )
        context = {
            "request": request,
            "user": user,
            "verify_link": verify_link,
        }

        # Select email template based on language
        template_name = f"emails/verify_email.{user_lang}.html"

        message = MessageSchema(
            subtype=MessageType.html,
            recipients=[user.email],
            subject="Email Verification Request",  # TODO: Add i18n support for email subjects
            template_body=context,
        )
        await get_sender().send_message(message, template_name=template_name)

        # Update sent time
        await self.user_db.update(
            user, {"last_verification_email_sent_at": datetime.now(UTC)}
        )

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        if not settings.MAIL_ENABLED:
            logger.info("MAIL_ENABLED is false; skipping password reset email")
            return

        # Check rate limit
        self._check_email_rate_limit(
            user.last_password_reset_email_sent_at, "password reset"
        )

        # Check if user has valid email
        if not user.email:
            logger.warning(
                f"Attempted to send password reset email to user {user.id} but user has no email address"
            )
            return

        # Detect user language preference
        user_lang = detect_language(user.language, request)

        reset_password_link = (
            f"{str(settings.FRONTEND_URL).rstrip('/')}/reset-password?token={token}"
        )
        context = {
            "request": request,
            "user": user,
            "reset_password_link": reset_password_link,
        }

        # Select email template based on language
        template_name = f"emails/reset_password.{user_lang}.html"

        message = MessageSchema(
            subtype=MessageType.html,
            recipients=[user.email],
            subject="Password Reset Request",  # TODO: Add i18n support for email subjects
            template_body=context,
        )
        await get_sender().send_message(message, template_name=template_name)

        # Update sent time
        await self.user_db.update(
            user, {"last_password_reset_email_sent_at": datetime.now(UTC)}
        )

    async def oauth_login_or_create(
        self,
        provider: OAuthProvider,
        provider_user_info: dict[str, Any],
        oauth_token: dict[str, Any],
    ) -> tuple[User, bool]:
        """
        OAuth Login or Create User

        Returns:
            tuple[User, bool]: (User object, Is new OAuth link)
        """
        try:
            # Import inside function to avoid circular import
            from .oauth_service import OAuthService

            provider_user_id = str(provider_user_info.get("id"))
            email = provider_user_info.get("email")
            username = (
                provider_user_info.get("login")
                or provider_user_info.get("username")
                or provider_user_info.get("name")
            )

            logger.info(
                f"OAuth login/create process started - provider: {provider.name}, user_id: {provider_user_id}, email: {email}, username: {username}"
            )

            # Create OAuth service instance
            oauth_service = OAuthService(self.user_db.session)

            # 1. Check if already linked (Highest priority)
            logger.debug(
                f"Checking existing OAuth link for provider {provider.id} and user {provider_user_id}"
            )
            oauth_link = await oauth_service.get_oauth_link(
                provider.id, provider_user_id
            )
            if oauth_link:
                logger.info(
                    f"Found existing OAuth link - user_id: {oauth_link.user_id}"
                )
                # Update token info
                await oauth_service.update_oauth_link_token(oauth_link, oauth_token)
                user = await self.get(oauth_link.user_id)
                logger.info(
                    f"OAuth login successful for existing link - user: {user.id}"
                )
                return user, False  # Not a new OAuth link

            # 2. Try multi-strategy matching to find existing user
            existing_user = await self._find_existing_user_for_oauth(
                email, username, provider_user_info
            )

            if existing_user:
                # Link to existing user
                user = existing_user
                logger.info(f"Linking OAuth account to existing user: {user.id}")
                is_new_oauth_link = True  # New OAuth link to existing user
            else:
                # Create new user
                user = await self._create_oauth_user(
                    provider, provider_user_id, email, username, provider_user_info
                )
                is_new_oauth_link = True  # New user, new OAuth link

            # 3. Create OAuth link
            logger.debug(
                f"Creating OAuth link for user {user.id} and provider {provider.id}"
            )
            await oauth_service.create_oauth_link(
                user_id=user.id,
                provider=provider,
                provider_user_info=provider_user_info,
                token_data=oauth_token,
            )
            logger.info(
                f"OAuth link created successfully for user {user.id} and provider {provider.name}"
            )

            return user, is_new_oauth_link
        except Exception as e:
            logger.error(
                f"OAuth login/create failed - provider: {provider.name}, "
                f"user_id: {provider_user_info.get('id')}, "
                f"email: {provider_user_info.get('email')}, "
                f"error: {e!s}",
                exc_info=True,
            )
            raise

    async def _find_existing_user_for_oauth(
        self,
        email: str | None,
        username: str | None,
        provider_user_info: dict[str, Any],
    ) -> User | None:
        """
        Find existing user using multi-strategy

        Args:
            email: Email returned by OAuth provider
            username: Username returned by OAuth provider
            provider_user_info: Complete OAuth user info

        Returns:
            Found user object or None
        """

        # Strategy 1: Match by email (Most reliable)
        if email:
            try:
                logger.debug(f"Checking if user exists with email: {email}")
                existing_user = await self.get_by_email(email)
                logger.info(
                    f"Found existing user with email {email} - user_id: {existing_user.id}"
                )
                return existing_user
            except exceptions.UserNotExists:
                logger.debug(f"No existing user found with email: {email}")
        else:
            logger.debug("No email provided by OAuth provider")

        # Strategy 2: Match by username (Current User model does not support username field)
        # Note: Use with caution as usernames may not be unique or prone to conflicts
        # if username and hasattr(User, 'username'):
        #     # If User model has username field and supports query
        #     # Add username matching logic here
        #     pass

        # Strategy 3: Match by other unique identifiers (if OAuth provider provides phone etc.)
        # phone = provider_user_info.get('phone')
        # if phone and hasattr(User, 'phone'):
        #     # If User model has phone field and supports query
        #     # Add phone matching logic here
        #     pass

        # TODO: Add more matching strategies in the future
        # - Match by real-name verification info
        # - Match by device fingerprint
        # - Match by user active linking

        logger.debug("No existing user found through any matching strategy")
        return None

    async def _create_oauth_user(
        self,
        provider: OAuthProvider,
        provider_user_id: str,
        email: str | None,
        username: str | None,
        provider_user_info: dict[str, Any],
    ) -> User:
        """
        Create new user for OAuth

        Args:
            provider: OAuth provider
            provider_user_id: Provider user ID
            email: Email
            username: Username
            provider_user_info: Complete OAuth user info

        Returns:
            Created user object
        """

        # Handle email address - Best practice: Use real email or None
        if email:
            user_email = email
            logger.info(f"Creating OAuth user with email: {email}")
        else:
            # Check if creating user without email is allowed
            if not settings.OAUTH_CREATE_USER_WITHOUT_EMAIL:
                logger.error(
                    f"OAuth provider {provider.name} did not provide email and OAUTH_CREATE_USER_WITHOUT_EMAIL is disabled"
                )
                raise ValueError(
                    "Email is required for user creation but not provided by OAuth provider"
                )

            # Best practice: Do not generate fake email, set to None directly
            # Pros:
            # 1. Data integrity - No fake info stored
            # 2. Clear user status - System knows user has no email
            # 3. Compliance - No fake personal info stored
            # 4. Better UX - User can add real email later
            user_email = None
            logger.info(
                f"Creating OAuth user without email - provider: {provider.name}, user_id: {provider_user_id}"
            )

        # Get name and avatar from mapped OAuth user info
        # Note: These fields should be mapped via provider.user_mapping configuration
        name = provider_user_info.get("name") or username
        avatar_url = provider_user_info.get("avatar")

        logger.info(
            f"Creating OAuth user with name: '{name}', avatar_url: '{avatar_url}'"
        )

        # Create user data object
        from .api.v1.schemas import UserCreate

        user_create_data = UserCreate(
            email=user_email,
            password=self._generate_random_password(),
            name=name,
            avatar_url=avatar_url,
            is_verified=not settings.OAUTH_REQUIRE_EMAIL_VERIFICATION,  # Determined by config and whether real email exists
            is_active=True,
        )

        # Current User model does not support username field, uncomment if needed in future
        # if username and hasattr(User, 'username'):
        #     # Ensure username uniqueness
        #     unique_username = await self._generate_unique_username(username, provider.name)
        #     # Note: If username is enabled, need to add username field to UserCreate model
        #     # user_create_data.username = unique_username

        logger.info(f"Creating new user for OAuth - email: {user_email}")

        # Create user
        user = await self.create(user_create_data)
        logger.info(f"New user created successfully - user_id: {user.id}")

        return user

    async def _generate_unique_username(
        self, base_username: str, provider_name: str
    ) -> str:
        """
        Generate unique username (Current User model does not support username field, this method is reserved)

        Args:
            base_username: Base username
            provider_name: Provider name

        Returns:
            Unique username
        """
        # Clean username, remove special characters
        import re

        clean_username = re.sub(r"[^\w\-_.]", "", base_username.lower())

        # If empty after cleaning, use provider name
        if not clean_username:
            clean_username = provider_name.lower()

        # If User model supports username field in future, implement this logic
        # Currently return cleaned username directly
        return clean_username or f"{provider_name}_user"

    def _generate_random_password(self) -> str:
        """Generate random password"""
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(32))

    async def authenticate(self, credentials) -> User | None:
        """
        Override authenticate method to support Django password format
        and implement account lockout for brute force protection.

        Need to check password format before password_helper.verify_and_update,
        because Django format will cause UnknownHashError
        """
        logger.debug(f"Authenticating user with email: {credentials.username}")
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            logger.debug(
                f"Authentication failed: user {credentials.username} not found"
            )
            # Run password hash to prevent timing attacks
            self.password_helper.hash(credentials.password)
            return None

        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now(UTC):
            logger.warning(
                f"Authentication attempt on locked account: {credentials.username}"
            )
            raise AccountLockedError(user.locked_until)

        # Call validate_password first to handle different formats
        try:
            await self.validate_password(credentials.password, user)
            logger.info(
                f"User {user.id} ({credentials.username}) authenticated successfully"
            )

            # Reset failed attempts on successful login
            if user.failed_login_attempts > 0:
                await self.user_db.update(
                    user, {"failed_login_attempts": 0, "locked_until": None}
                )

        except exceptions.InvalidPasswordException:
            logger.warning(
                f"Authentication failed for user {credentials.username}: invalid password"
            )

            # Increment failed login attempts
            new_attempts = (user.failed_login_attempts or 0) + 1
            update_data: dict[str, Any] = {"failed_login_attempts": new_attempts}

            # Lock account if max attempts exceeded
            if new_attempts >= settings.ACCOUNT_LOCKOUT_MAX_ATTEMPTS:
                locked_until = datetime.now(UTC) + timedelta(
                    minutes=settings.ACCOUNT_LOCKOUT_DURATION_MINUTES
                )
                update_data["locked_until"] = locked_until
                logger.warning(
                    f"Account locked for {credentials.username} until {locked_until} "
                    f"after {new_attempts} failed attempts"
                )

            await self.user_db.update(user, update_data)
            return None

        if not user.is_active:
            logger.warning(
                f"Authentication failed for user {credentials.username}: account not active"
            )
            return None

        return user

    async def validate_password(
        self, password: str, user: Union["UserCreate", User]
    ) -> None:
        """
        Validate password

        Args:
            password: Password to validate
            user: User object (login) or UserCreate object (create user)
        """
        # If it is UserCreate object (create user), only need to call parent class password validation
        # No need to check hashed_password, because it does not exist yet
        if not isinstance(user, User):
            # This is create user scenario, call parent class password strength validation
            await super().validate_password(password, user)
            return

        # The following is User object validation logic (login scenario)
        # Use standard bcrypt validation
        verified, updated_password_hash = self.password_helper.verify_and_update(
            password, user.hashed_password
        )
        if not verified:
            raise exceptions.InvalidPasswordException(
                reason="Password validation failed"
            )

        # If password hash needs update (e.g. parameters changed)
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)
