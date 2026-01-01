/// <reference types="node" />
/**
 * Playwright global setup for E2E tests.
 *
 * This file runs once before all tests to ensure a clean test environment.
 * It removes old test data to prevent state leakage between test runs.
 */

import fs from "fs";
import path from "path";

// E2E test data directory (relative to frontend/)
const E2E_DATA_DIR = path.resolve(__dirname, "../../.e2e-data");

async function globalSetup(): Promise<void> {
  console.log("[E2E Setup] Cleaning test data directory...");

  // In CI, each run gets a unique directory so no cleanup needed
  if (process.env.CI) {
    console.log("[E2E Setup] CI mode - using isolated run directory");
    return;
  }

  // For local development, clean the e2e database to start fresh
  // This ensures "first user becomes admin" works correctly
  const dbPath = path.join(E2E_DATA_DIR, "e2e.db");

  try {
    if (fs.existsSync(dbPath)) {
      fs.unlinkSync(dbPath);
      console.log("[E2E Setup] Removed existing e2e.db");
    }

    // Also remove SQLite journal/WAL files if they exist
    const walPath = dbPath + "-wal";
    const shmPath = dbPath + "-shm";
    const journalPath = dbPath + "-journal";

    if (fs.existsSync(walPath)) fs.unlinkSync(walPath);
    if (fs.existsSync(shmPath)) fs.unlinkSync(shmPath);
    if (fs.existsSync(journalPath)) fs.unlinkSync(journalPath);

    // Optionally clean Chroma data for full reset
    const chromaPath = path.join(E2E_DATA_DIR, "chroma");
    if (fs.existsSync(chromaPath)) {
      // Remove Chroma SQLite file but keep directory structure
      const chromaDbPath = path.join(chromaPath, "chroma.sqlite3");
      if (fs.existsSync(chromaDbPath)) {
        fs.unlinkSync(chromaDbPath);
        console.log("[E2E Setup] Removed existing Chroma database");
      }
    }

    console.log("[E2E Setup] Test data cleaned successfully");
  } catch (error) {
    console.warn("[E2E Setup] Warning: Could not clean test data:", error);
    // Continue anyway - tests might still work
  }
}

export default globalSetup;
