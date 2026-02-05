from app.routes import parser as parser_routes


def test_parse_list_request_reuses_parse_request():
    assert parser_routes.ParseListRequest is parser_routes.ParseRequest
