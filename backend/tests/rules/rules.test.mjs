// Firestore rules tests. Every direct client read and write must fail,
// because only the backend touches Firestore. Needs the emulator running:
// firebase emulators:start --only firestore (from the repo root).
import { readFileSync } from "node:fs";
import path from "node:path";
import { after, before, describe, it } from "node:test";
import {
  assertFails,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import { deleteDoc, doc, getDoc, setDoc } from "firebase/firestore";

const PROJECT_ID = "fix-it-proper-test";
const RULES_PATH = path.join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "firestore.rules",
);

let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: {
      rules: readFileSync(RULES_PATH, "utf8"),
      host: "127.0.0.1",
      port: 8080,
    },
  });
});

after(async () => {
  await testEnv.cleanup();
});

function anonDb() {
  return testEnv.unauthenticatedContext().firestore();
}

function userDb() {
  return testEnv
    .authenticatedContext("user-1", { email: "user-1@example.com" })
    .firestore();
}

describe("firestore.rules denies all direct client access", () => {
  it("denies anonymous reads", async () => {
    await assertFails(getDoc(doc(anonDb(), "reports/req-1")));
  });

  it("denies anonymous writes", async () => {
    await assertFails(
      setDoc(doc(anonDb(), "contact_messages/m1"), { message: "hi" }),
    );
  });

  it("denies signed in reads of own user record", async () => {
    await assertFails(getDoc(doc(userDb(), "users/user-1")));
  });

  it("denies signed in writes", async () => {
    await assertFails(
      setDoc(doc(userDb(), "reports/req-2"), { user_id: "user-1" }),
    );
  });

  it("denies signed in deletes", async () => {
    await assertFails(deleteDoc(doc(userDb(), "reports/req-3")));
  });
});
