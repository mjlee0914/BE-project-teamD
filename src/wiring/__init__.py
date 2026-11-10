from fastapi import FastAPI

from wiring.actor import wire_actor_dependencies
from wiring.auth import wire_auth_dependencies
from wiring.festival import wire_festival_dependencies
from wiring.payment import wire_payment_dependencies
from wiring.performance import wire_performance_dependencies
from wiring.reservation import wire_reservation_dependencies
from wiring.ticket import wire_ticket_dependencies
from wiring.user import wire_user_dependencies


# FastAPI Dependency Overrides 와이어링
def wire_dependencies(app: FastAPI) -> None:
    wire_actor_dependencies(app)
    wire_auth_dependencies(app)
    wire_festival_dependencies(app)
    wire_payment_dependencies(app)
    wire_performance_dependencies(app)
    wire_reservation_dependencies(app)
    wire_ticket_dependencies(app)
    wire_user_dependencies(app)
