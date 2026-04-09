import { task } from "@trigger.dev/sdk/v3";

const relayTaskId =
  typeof process.env.TRIGGER_RELAY_TASK_ID === "string" && process.env.TRIGGER_RELAY_TASK_ID.trim()
    ? process.env.TRIGGER_RELAY_TASK_ID.trim()
    : "postclipper-relay";

const relayPathRaw = process.env.POSTCLIPPER_RELAY_PATH?.trim() || "/internal/trigger-dev/relay";
const relayPath = relayPathRaw.startsWith("/") ? relayPathRaw : `/${relayPathRaw}`;

/**
 * Receives { jobName, args } from the PostClipper API (via Trigger REST),
 * then POSTs to your API relay so Arq picks up the job on your worker.
 *
 * Env: repository root `.env` (local `npm run trigger:dev`) or Trigger.dev → Environments:
 * POSTCLIPPER_EXECUTOR_URL, POSTCLIPPER_EXECUTOR_SECRET, optional TRIGGER_RELAY_TASK_ID, POSTCLIPPER_RELAY_PATH.
 */
export const postclipperRelay = task({
  id: relayTaskId,
  run: async (payload: { jobName: string; args: unknown[] }) => {
    const base = process.env.POSTCLIPPER_EXECUTOR_URL?.trim();
    const secret = process.env.POSTCLIPPER_EXECUTOR_SECRET;
    if (!base || !secret) {
      throw new Error(
        "Missing POSTCLIPPER_EXECUTOR_URL or POSTCLIPPER_EXECUTOR_SECRET (set in .env or Trigger.dev environment)"
      );
    }
    const url = `${base.replace(/\/$/, "")}${relayPath}`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-PostClipper-Executor-Secret": secret,
      },
      body: JSON.stringify({ job_name: payload.jobName, args: payload.args }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`Relay HTTP ${res.status}: ${t}`);
    }
    return (await res.json()) as { ok: boolean };
  },
});
