import assert from "node:assert/strict";
import test from "node:test";
import { monthlySeatCost } from "./quote.js";

test("monthly quote excludes suspended seats", () => {
  const seats = [
    { user: "Alex", status: "active" },
    { user: "Morgan", status: "suspended" },
    { user: "Sam", status: "active" },
  ];

  assert.equal(monthlySeatCost(seats, 30), 60);
});
