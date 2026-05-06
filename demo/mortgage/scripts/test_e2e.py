"""End-to-end test for the Mortgage Origination Demo (kind/k8s).

Walks through the full mortgage application journey via the customer
agent's WebSocket interface:
    1. Greeting           -> agent asks for BAN + PIN
    2. Authentication     -> Auth Agent verifies credentials via mesh
    3. Passport upload    -> KYC Agent verifies identity via mesh
    4. Payslip upload     -> Credit Agent assesses capacity via mesh
    5. Property details   -> Credit Agent makes lending decision via mesh
    6. Contract upload    -> Core Banking Agent disburses loan via mesh

Prerequisites: make mortgage-up
Usage:         python demo/mortgage/scripts/test_e2e.py [WS_URL]
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time
import uuid

import websockets

DEFAULT_WS_URL = "ws://localhost:8031/api/ws"


def _make_image_with_text(lines: list[str], width: int = 800, height: int = 500) -> bytes:
    """Render a white image with the given lines of text using Pillow.

    The mortgage demo's customer agent uses an LLM-vision call to extract
    fields from uploaded documents. A blank PNG is rejected as unreadable,
    so the test must produce an image whose text content matches what the
    agent expects (passport name + number, payslip salary, contract).
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()

    y = 30
    for line in lines:
        draw.text((30, y), line, fill=(0, 0, 0), font=font)
        y += 42

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_passport_image() -> bytes:
    return _make_image_with_text([
        "PASSPORT",
        "REPUBLIC OF DEMOLAND",
        "",
        "Surname:    SMITH",
        "Given Name: JANE",
        "Document #: P12345678",
        "Date of Birth: 1985-06-15",
        "Nationality: DEMOLANDIAN",
    ])


def make_payslip_image() -> bytes:
    return _make_image_with_text([
        "PAYSLIP",
        "ACME CORPORATION",
        "",
        "Employee: JANE SMITH",
        "Period:   January 2026",
        "",
        "Annual Salary: 60000",
        "Net Pay:       4200",
        "Currency: GBP",
    ])


def make_contract_image() -> bytes:
    return _make_image_with_text([
        "PURCHASE CONTRACT",
        "",
        "Buyer:  JANE SMITH",
        "Seller: PROPCO LIMITED",
        "",
        "Property: 123 Demo Street, London",
        "Price:    300000 GBP",
        "Deposit:  50000 GBP",
        "",
        "Signed: JANE SMITH",
    ])


class TestRunner:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.session_id = f"e2e-test-{os.getpid()}-{int(time.time())}"
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def report_pass(self, msg: str) -> None:
        print(f"  PASS  {msg}")
        self.passed += 1

    def report_fail(self, step: str, msg: str) -> None:
        print(f"  FAIL  {msg}")
        self.failed += 1
        self.errors.append(f"Step {step}: {msg}")

    async def collect_response(self, ws) -> tuple[str, str]:
        """Collect a stream of message_chunks until message_end. Returns (text, phase)."""
        text_parts: list[str] = []
        phase = ""
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=180)
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "message_chunk":
                text_parts.append(msg.get("text", ""))
            elif mtype == "message_end":
                phase = msg.get("phase", "")
                break
            elif mtype in ("status", "history"):
                continue
            else:
                continue
        return "".join(text_parts), phase

    def assert_phase(self, step: str, expected: str, actual: str) -> None:
        if actual == expected:
            self.report_pass(f"phase={actual}")
        else:
            self.report_fail(step, f"expected phase {expected}, got {actual}")

    def assert_contains(self, step: str, needle: str, haystack: str) -> None:
        if needle.lower() in haystack.lower():
            self.report_pass(f"response contains '{needle}'")
        else:
            self.report_fail(step, f"response missing '{needle}' (got: {haystack[:120]!r})")

    async def send_message(self, ws, text: str, file_bytes: bytes | None = None) -> tuple[str, str]:
        if file_bytes is not None:
            payload = {
                "type": "message_with_file",
                "text": text,
                "file": {
                    "data": base64.b64encode(file_bytes).decode("ascii"),
                    "media_type": "image/png",
                    "name": "doc.png",
                },
            }
        else:
            payload = {"type": "message", "text": text}
        await ws.send(json.dumps(payload))
        return await self.collect_response(ws)

    async def run(self) -> int:
        print("Mortgage Demo - End-to-End Test")
        print("================================")
        print(f"WS URL:     {self.ws_url}")
        print(f"Session ID: {self.session_id}")
        print()
        print("Connecting...")

        try:
            async with websockets.connect(self.ws_url, max_size=None) as ws:
                # Init
                await ws.send(json.dumps({"type": "init", "session_id": self.session_id}))

                # Drain history + welcome message
                got_history = False
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    msg = json.loads(raw)
                    if msg.get("type") == "history":
                        got_history = True
                        continue
                    if msg.get("type") == "message_chunk":
                        # Welcome message starting — collect until message_end
                        # (re-feed by reading remaining chunks)
                        rest_text = msg.get("text", "")
                        while True:
                            raw2 = await asyncio.wait_for(ws.recv(), timeout=30)
                            msg2 = json.loads(raw2)
                            if msg2.get("type") == "message_chunk":
                                rest_text += msg2.get("text", "")
                            elif msg2.get("type") == "message_end":
                                break
                        break
                    if msg.get("type") == "message_end":
                        break

                if not got_history:
                    self.report_fail("connect", "did not receive history frame")
                else:
                    self.report_pass("WebSocket handshake + history received")
                print()

                passport_img = make_passport_image()
                payslip_img = make_payslip_image()
                contract_img = make_contract_image()

                # Step 1: Greeting
                print("Step 1: Greeting")
                text, phase = await self.send_message(ws, "Hello, I would like to apply for a mortgage please")
                self.assert_phase("1", "AUTHENTICATING", phase)
                self.assert_contains("1", "BAN", text)
                print()

                # Step 2: Authentication
                print("Step 2: Authentication (BAN + PIN)")
                text, phase = await self.send_message(ws, "My BAN is 12345678 and my PIN is 1234")
                self.assert_phase("2", "AWAITING_PASSPORT", phase)
                self.assert_contains("2", "passport", text)
                print()

                # Step 3: Passport upload
                print("Step 3: Passport upload (KYC verification)")
                text, phase = await self.send_message(ws, "Here is my passport", file_bytes=passport_img)
                self.assert_phase("3", "AWAITING_PAYSLIP", phase)
                self.assert_contains("3", "payslip", text)
                print()

                # Step 4: Payslip upload
                print("Step 4: Payslip upload (credit assessment)")
                text, phase = await self.send_message(
                    ws,
                    "Here is my payslip showing annual salary of 60000",
                    file_bytes=payslip_img,
                )
                self.assert_phase("4", "PRESENTING_OFFER", phase)
                self.assert_contains("4", "270", text)  # 60000 * 4.5 = 270,000
                print()

                # Step 5: Property details
                print("Step 5: Property details (credit decision)")
                text, phase = await self.send_message(
                    ws,
                    "The property is at 123 Demo Street, London, worth 300000 and I have a deposit of 50000",
                )
                self.assert_phase("5", "AWAITING_CONTRACT", phase)
                self.assert_contains("5", "250", text)  # 300000 - 50000 = 250,000 loan
                print()

                # Step 6: Contract upload
                print("Step 6: Contract upload (loan disbursement)")
                text, phase = await self.send_message(
                    ws,
                    "Here is the signed purchase contract",
                    file_bytes=contract_img,
                )
                self.assert_phase("6", "COMPLETED", phase)
                print()

        except Exception as e:
            self.report_fail("connection", f"WebSocket error: {e}")

        # Summary
        print("================================")
        total = self.passed + self.failed
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.failed:
            print()
            print("Failures:")
            for err in self.errors:
                print(f"  {err}")
            return 1
        print()
        print("Mortgage demo end-to-end test passed.")
        return 0


def main() -> int:
    ws_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WS_URL
    runner = TestRunner(ws_url)
    return asyncio.run(runner.run())


if __name__ == "__main__":
    sys.exit(main())
