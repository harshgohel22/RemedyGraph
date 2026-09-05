from app.evaluation.runner import format_report, run_heldout


def main() -> None:
    report = run_heldout()
    print(format_report(report))


if __name__ == "__main__":
    main()
