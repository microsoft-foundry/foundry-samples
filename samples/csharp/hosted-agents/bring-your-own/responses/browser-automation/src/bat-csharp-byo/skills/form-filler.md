# Form Filler Skill

1. Create or reuse a browser session and preserve its `browserSessionId`.
2. Use the discovered navigation tool to open the form.
3. Take a browser snapshot and identify every required field.
4. Prefer the discovered form-fill tool when filling several fields; otherwise use the discovered type, select, check, and click tools as appropriate.
5. Take a fresh snapshot after navigation, dialogs, or any page-changing action.
6. For date pickers, open the picker, snapshot its UI, navigate to the requested month and day, and verify the selected date. If the picker does not open, try entering the date in the format expected by the field.
7. If a field rejects input, try clicking it first, clearing and refilling it, or using the correct format. Never skip required fields.
8. After filling all required values, click Next, Continue, or Submit as requested. Snapshot after submission and repeat for every page in the form.
9. Verify the final result. Report OTP, CAPTCHA, authentication, approval, or missing user data as a blocker without fabricating values.
10. Keep the named browser open while waiting and after completion. Resume in that same browser after the user replies. Close only on explicit user request.

Use the requested session name in `browserSessionId`, or omit it for the default. Use only browser tool names and schemas returned by MCP discovery.
