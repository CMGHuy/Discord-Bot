import json
import sys


def main():
    data = json.load(sys.stdin)
    model = data.get("model", {}).get("display_name", "")
    ctx = data.get("context_window", {}).get("used_percentage", "")
    rate_limits = data.get("rate_limits", {})
    five_hour = rate_limits.get("five_hour", {})
    seven_day = rate_limits.get("seven_day", {})
    fields = (
        model,
        ctx,
        five_hour.get("used_percentage", ""),
        five_hour.get("resets_at", ""),
        seven_day.get("used_percentage", ""),
        seven_day.get("resets_at", ""),
    )
    print("\t".join(str(v) for v in fields))


if __name__ == "__main__":
    main()
