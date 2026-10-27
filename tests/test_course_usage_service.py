from datetime import date

from src.course_usage_service import Delivery


def test_delivery_completed_before_deadline_is_reported_as_completed():
    delivery = Delivery("school-17", "audio-editing", date(2026, 10, 30), date(2026, 10, 28))

    assert delivery.status == "completed"
