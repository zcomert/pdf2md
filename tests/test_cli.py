import pytest
from src.cli import build_parser, main

def test_positional_and_option_input_rejected():
    with pytest.raises(SystemExit):
        main(["papers", "--input", "other"])

def test_include_is_repeatable():
    args = build_parser().parse_args(["--include", "a.pdf", "--include", "b.pdf"])
    assert args.include == ["a.pdf", "b.pdf"]
