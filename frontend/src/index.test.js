import assert from "node:assert/strict";
import test from "node:test";

import { getFrontendStatus } from "./index.js";

test("getFrontendStatus returns scaffold metadata", () => {
  assert.deepEqual(getFrontendStatus(), {
    service: "open-messenger-frontend",
    status: "scaffolded"
  });
});
