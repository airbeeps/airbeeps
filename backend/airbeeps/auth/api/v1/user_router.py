"""
Authentication API Router
"""

import logging

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.auth import fastapi_users
from airbeeps.auth.auth_helpers import clear_auth_cookies, set_auth_cookies
from airbeeps.auth.manager import AccountLockedError, UserManager, get_user_manager
from airbeeps.config import settings
from airbeeps.database import get_async_session
from airbeeps.system_config.service import config_service
from airbeeps.users.models import User

from .schemas import ChangePasswordRequest, UserRead, UserRegisterRequest

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

# Rate limiter for auth endpoints (stricter limits for security)
limiter = Limiter(key_func=get_remote_address)


class LoginResponse(BaseModel):
    """Login Response"""

    access_token: str
    token_type: str = "bearer"


class LogoutResponse(BaseModel):
    """Logout Response"""

    success: bool
    message: str = "Logged out successfully"


@router.post("/login", response_model=LoginResponse, name="auth:jwt.login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """
    User Login (Supports Refresh Token)

    Login with email/password, returns Access Token and Refresh Token (via Cookie)
    """
    # Verify user (may raise AccountLockedError)
    try:
        user = await user_manager.authenticate(credentials)
    except AccountLockedError as e:
        logger.warning(
            f"Login blocked for locked account: {credentials.username}, "
            f"remaining: {e.remaining_seconds}s"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "LOGIN_ACCOUNT_LOCKED",
                "message": f"Account temporarily locked. Try again in {e.remaining_seconds} seconds.",
                "remaining_seconds": e.remaining_seconds,
            },
        )

    if user is None or not user.is_active:
        logger.warning(f"Login failed for username: {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS"
        )

    # Only enforce email verification when email is enabled.
    # When MAIL_ENABLED is false, verification is bypassed to avoid dead-end UX.
    if settings.MAIL_ENABLED and not user.is_verified:
        logger.warning(f"Login attempted with unverified account: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_USER_NOT_VERIFIED"
        )

    # Set auth cookies (Access Token + Refresh Token)
    await set_auth_cookies(response, user, request, session)

    # Trigger post-login hooks
    await user_manager.on_after_login(user, request, response)

    logger.info(f"User {user.id} logged in successfully")

    # Return Access Token (Also in Cookie, here for compatibility)
    from airbeeps.auth.fastapi_users import get_jwt_strategy

    jwt_strategy = get_jwt_strategy()
    access_token = await jwt_strategy.write_token(user)

    return LoginResponse(access_token=access_token, token_type="bearer")


@router.post("/logout", response_model=LogoutResponse, name="auth:jwt.logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(None, alias="refresh-token"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    User Logout (Revoke Refresh Token)

    Clear Cookie and revoke current Refresh Token
    """
    # Clear Cookie and revoke token
    await clear_auth_cookies(response, refresh_token, session)

    logger.info("User logged out successfully")

    return LogoutResponse(success=True)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_create: UserRegisterRequest,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """
    User Registration
    """
    # Check if registration is enabled
    registration_enabled = await config_service.get_config_value(
        session, "registration_enabled", default=True
    )

    # Handle string "false"
    if (
        isinstance(registration_enabled, str)
        and registration_enabled.lower() == "false"
    ):
        registration_enabled = False

    if not registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="REGISTER_DISABLED"
        )

    # Convert back to the internal UserCreate schema
    # user_create is already UserRegisterRequest which inherits from UserCreate
    # but we need to make sure we pass the right data to user_manager.create

    try:
        created_user = await user_manager.create(
            user_create, safe=True, request=request
        )
    except exceptions.UserAlreadyExists:
        # Security: Use generic error to prevent user enumeration
        # Attackers cannot determine if an email is already registered
        logger.info(f"Registration attempt with existing email: {user_create.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="REGISTER_INVALID_REQUEST",
        )
    except exceptions.InvalidPasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "REGISTER_INVALID_PASSWORD",
                "reason": e.reason,
            },
        )

    return UserRead.model_validate(created_user)


class ForgotPasswordRequest(BaseModel):
    """Forgot Password Request"""

    email: str


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Forgot Password
    """
    try:
        user = await user_manager.get_by_email(body.email)
        await user_manager.forgot_password(user, request)
    except exceptions.UserNotExists:
        # For security, return success even if user does not exist
        pass


# Verification router (No change needed, keep as is)
# Register router - Use custom register router
# router.include_router(
#     fastapi_users.get_register_router(UserRead, UserCreate)
# )

# Verification router
router.include_router(fastapi_users.get_verify_router(UserRead))


# Reset password router - Keep reset-password endpoint
class ResetPasswordRequest(BaseModel):
    """Reset Password Request"""

    token: str
    password: str


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Reset Password
    """
    try:
        await user_manager.reset_password(body.token, body.password, request)
    except (
        exceptions.InvalidResetPasswordToken,
        exceptions.UserNotExists,
        exceptions.UserInactive,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RESET_PASSWORD_BAD_TOKEN",
        )
    except exceptions.InvalidPasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "RESET_PASSWORD_INVALID_PASSWORD",
                "reason": e.reason,
            },
        )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(fastapi_users.current_user(active=True)),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Change Password (Login required)

    User must provide old password to change to new password
    """
    try:
        # Verify old password
        await user_manager.validate_password(body.old_password, user)
    except exceptions.InvalidPasswordException:
        logger.warning(
            f"Change password failed - incorrect old password for user {user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CHANGE_PASSWORD_INCORRECT_OLD_PASSWORD",
        )

    # Verify new password strength
    try:
        # Create temporary UserCreate object for password strength verification
        from .schemas import UserCreate

        temp_user_create = UserCreate(
            email=user.email,
            password=body.new_password,
        )
        await user_manager.validate_password(body.new_password, temp_user_create)
    except exceptions.InvalidPasswordException as e:
        logger.warning(
            f"Change password failed - invalid new password for user {user.id}: {e.reason}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CHANGE_PASSWORD_INVALID_PASSWORD",
                "reason": e.reason,
            },
        )

    # Update password
    hashed_password = user_manager.password_helper.hash(body.new_password)
    await user_manager.user_db.update(user, {"hashed_password": hashed_password})

    logger.info(f"Password changed successfully for user {user.id}")

    return {"success": True, "message": "Password changed successfully"}
