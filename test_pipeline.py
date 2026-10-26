"""Local smoke check for OpenCV 5 perception and the human approval gate."""
from pathlib import Path

import cv2
from shelfwatch import agent, vision

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"


def load(name):
    image = cv2.imread(str(SAMPLES / name))
    if image is None:
        raise AssertionError(f"Could not load required sample: {name}")
    return image


def main():
    assert cv2.__version__.split(".", 1)[0] == "5", f"OpenCV 5 is required; found {cv2.__version__}"
    reference = load("reference.jpg")
    current = load("current_3_missing.jpg")
    output = agent.run(reference, current)

    expected_gaps = {(0, 2), (1, 4), (2, 0)}
    expected_review = {(1, 2)}
    actual_gaps = set(output["gaps"])
    actual_review = set(output["uncertain"])
    assert output["status"] == "awaiting_approval", output["status"]
    assert actual_gaps == expected_gaps, f"Expected {expected_gaps}, got {actual_gaps}"
    assert actual_review == expected_review, f"Expected review {expected_review}, got {actual_review}"
    assert any(event["event"] == "active_reinspection" for event in output["trace"]), "Agent did not re-inspect an uncertain cell"
    assert any(event["event"] == "human_approval_gate" for event in output["trace"]), "No human approval gate was recorded"

    overlay = vision.overlay(output["aligned"], output["results"], 3, 6)
    if not cv2.imwrite(str(SAMPLES / "result_overlay.jpg"), overlay):
        raise AssertionError("Could not save the annotated result image")

    rejected = agent.run(reference, load("current_unaligned.jpg"))
    assert rejected["status"] == "recapture_requested", rejected["status"]

    approved = agent.approve(output["order_id"])
    assert approved and approved["approved"] is True
    assert agent.approve(output["order_id"]) is None, "Duplicate approval must be rejected"

    print(f"PASS | OpenCV {cv2.__version__} | alignment={output['confidence']:.2f}")
    print("PASS | confirmed missing cells:", sorted(actual_gaps))
    print("PASS | partial occlusion triggered targeted reinspection:", sorted(actual_review))
    print("PASS | unalignable photo requested a retake")
    print("PASS | draft requires one human approval and is not externally sent")
    print("Saved overlay:", SAMPLES / "result_overlay.jpg")


if __name__ == "__main__":
    main()
