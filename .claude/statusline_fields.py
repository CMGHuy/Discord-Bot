import json
import sys


def whole_pct(value):
    # rate_limits percentages arrive as floats with binary-representation
    # noise (e.g. 7.000000000000001) - these are whole-number percentages by
    # definition, so round rather than display the float artifact.
    if value == "":
        return ""
    return str(round(value))


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
        whole_pct(five_hour.get("used_percentage", "")),
        five_hour.get("resets_at", ""),
        whole_pct(seven_day.get("used_percentage", "")),
        seven_day.get("resets_at", ""),
    )
    print("\t".join(str(v) for v in fields))


if __name__ == "__main__":
    main()
