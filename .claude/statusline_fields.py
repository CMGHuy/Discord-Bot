import json
import sys


def main():
    data = json.load(sys.stdin)
    model = data.get("model", {}).get("display_name", "")
    ctx = data.get("context_window", {}).get("used_percentage", "")
    five_hour = data.get("rate_limits", {}).get("five_hour", {})
    sess = five_hour.get("used_percentage", "")
    resets_at = five_hour.get("resets_at", "")
    print("\t".join(str(v) for v in (model, ctx, sess, resets_at)))


if __name__ == "__main__":
    main()
