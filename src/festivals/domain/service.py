# [현재 사용하지 않는 파일]
# 기간 겹침 규칙은 application/service.py에서 repository.exists_overlapping()으로 DB에 바로 물어봄

# domain service란?
# DB 없이, 여러 객체를 받아서 규칙만 판단하는 곳 (계산기 역할)
# 꺼내오기/저장/commit은 application/service.py가 담당

# 규칙을 어디에 넣을까?
# 1. 축제 하나만 봐도 아는 규칙 -> domain/festival.py의 Festival 클래스 안
#    ex) 시작일 < 종료일, 이미 취소된 축제는 다시 취소 불가
# 2. 다른 축제들과 비교해야 아는 규칙 -> 이 파일 (또는 application/service.py)
#    ex) 같은 장소에서 기간이 겹치는 축제는 만들지 못한다
#    이 파일을 쓴다면: application service가 다른 축제들을 꺼내서 넘겨주고, 여기서는 비교만 함
