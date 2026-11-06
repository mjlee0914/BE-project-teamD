from festivals.domain.repository import FestivalRepository

class ReservationService:
    def __init__(self, reservation_repo, festival_reader):
        self._reservation_repo = reservation_repo
        self._festival_reader = festival_reader

    