import "dotenv/config";
import { defineConfig } from "@trigger.dev/sdk/v3";

const project = process.env.TRIGGER_PROJECT_REF?.trim();
if (!project) {
  throw new Error("Set TRIGGER_PROJECT_REF in repository root .env");
}

export default defineConfig({
  project,
  dirs: ["./trigger"],
  // Required by Trigger.dev CLI >= 4.4.x
  maxDuration: 60,
  retries: {
    enabledInDev: true,
    default: {
      maxAttempts: 3,
      minTimeoutInMs: 1000,
      maxTimeoutInMs: 30_000,
      factor: 2,
      randomize: true,
    },
  },
});
