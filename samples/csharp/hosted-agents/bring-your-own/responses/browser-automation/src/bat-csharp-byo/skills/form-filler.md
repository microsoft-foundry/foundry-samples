# Form Filler Skill

1. Create or reuse a browser session and preserve its `browserSessionId`.
2. Use the discovered navigation tool to open the form.
3. Take a browser snapshot and identify every required field.
4. Identify each control type before choosing a tool. Batch compatible text-entry fields with the discovered form-fill tool. Handle native selects, checkboxes, and radio buttons separately with the appropriate discovered tools. Distinguish an editable datalist input from a native select. Check the current checked or selected state before clicking so an already-correct value is not toggled.
5. Take a fresh snapshot after navigation, dialogs, or any page-changing action.
6. For date pickers, open the picker, snapshot its UI, navigate to the requested month and day, and verify the selected date. If the picker does not open, try entering the date in the format expected by the field.
7. If filling fails, take a full snapshot without a target and inspect which fields already changed. Refill only missing or incorrect values using fresh refs and the right control-specific tool; do not replay the whole batch. Never skip required fields.
8. Verify the supplied values before clicking Next, Continue, or Submit as requested. Snapshot after submission and repeat for every page in the form. If a click times out, check for navigation or confirmation before retrying; never submit again after confirmed success. If the outcome remains unknown, report that uncertainty instead of risking a duplicate submission.
9. Verify the final result. Report OTP, CAPTCHA, authentication, approval, or missing user data as a blocker without fabricating values.
10. Keep the named browser open while waiting and after completion. Resume in that same browser after the user replies. Close only on explicit user request.

Use the requested session name in `browserSessionId`, or omit it for the default. Use only browser tool names and schemas returned by MCP discovery.
