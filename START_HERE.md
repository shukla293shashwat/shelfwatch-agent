# Start here

1. Install Python 3.12 and extract the complete folder.
2. Double-click **start.bat** on Windows.
3. Open **http://127.0.0.1:8000/** after the server starts.
4. Click **Try synthetic demo** or **Try real-photo development example**.

For a manual upload, use `samples/current_3_missing.jpg` as current and `samples/reference.jpg` as reference. Expect three candidate gap cells and one review cell.

For your own photos, upload a stocked reference and a current view of the same shelf, then drag over the actual shelf area or enter its edges as percentages. Review the result before approving the local draft. No supplier order is sent.

The README explains the method and evidence. Version 2 improves the two known real-photo failures. A separate synthetic stress set passes 32/33 cases, with a partial occlusion still wrongly marked as a candidate gap. These are not real-store accuracy claims.

AWS activation and a verified live deployment are still required; see `deploy/aws/README.md`.
