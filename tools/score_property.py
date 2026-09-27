"""Evidence-aware property score. Does not infer field evidence from addresses."""

import argparse
import json
import math


WEIGHTS = {"quiet": 30, "sound": 20, "density": 15,
           "convenience": 15, "price": 15, "liquidity": 5}
GATES = ("inside_third_ring", "residential_clear_title", "structurally_safe",
         "no_major_road_noise", "not_above_commercial_street", "not_overcrowded",
         "acceptable_property_management", "adequate_daylight", "not_investment_only")


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected number")
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name}: invalid value")
    return value


def score(data):
    failures, unknown, warnings = [], [], []
    gates = data.get("gates", {})
    for key in GATES:
        value = gates.get(key)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"gates.{key}: expected boolean or null")
        if value is False:
            failures.append(key)
        elif value is None:
            unknown.append(key)

    for field, low, high in (("area_sqm", 40, 60), ("price_wan", 0.01, 50)):
        value = data.get(field)
        if value is None:
            unknown.append(field)
        else:
            number(value, field, 0.01)
            if not low <= value <= high:
                failures.append(field)
    floor, total, elevator = (data.get(k) for k in ("floor", "total_floors", "elevator"))
    for name, value in (("floor", floor), ("total_floors", total)):
        if value is None:
            unknown.append(name)
        elif number(value, name, 1) != int(value):
            raise ValueError(f"{name}: expected positive integer")
    if floor is not None and total is not None and floor > total:
        raise ValueError("floor exceeds total_floors")
    if elevator is not None and not isinstance(elevator, bool):
        raise ValueError("elevator: expected boolean or null")
    if elevator is None:
        unknown.append("elevator")
    elif elevator is False and floor is not None and floor > 3:
        failures.append("walkup_above_floor_3")

    area, price, supplied = (data.get(k) for k in ("area_sqm", "price_wan", "unit_price_yuan"))
    calculated = None
    if area is not None and price is not None:
        calculated = price * 10000 / area
    if supplied is not None:
        number(supplied, "unit_price_yuan", 0.01)
        if calculated is not None and abs(supplied - calculated) / calculated > 0.02:
            warnings.append("unit_price_mismatch_over_2_percent")
            unknown.append("price_data_consistency")

    confidence = data.get("price_evidence_confidence", "unknown")
    if confidence not in ("unknown", "low", "medium", "high"):
        raise ValueError("invalid price_evidence_confidence")
    ratings, evidence, points = data.get("ratings", {}), data.get("evidence", {}), {}
    missing_dimensions = []
    for key, weight in WEIGHTS.items():
        rating = ratings.get(key)
        if rating is not None:
            number(rating, f"ratings.{key}")
            if rating > 5:
                raise ValueError(f"ratings.{key}: maximum is 5")
        supported = isinstance(evidence.get(key), str) and bool(evidence[key].strip())
        if rating is None or not supported or (key == "price" and confidence == "unknown"):
            missing_dimensions.append(key)
        else:
            points[key] = round(rating / 5 * weight, 2)
    lower = round(sum(points.values()), 2)
    upper = round(lower + sum(WEIGHTS[k] for k in missing_dimensions), 2)
    complete = not unknown and not missing_dimensions
    if failures:
        grade, reason = "D", "hard_gate_failed"
    elif not complete:
        grade, reason = "C", "incomplete_evidence"
    elif lower < 55:
        grade, reason = "D", "score_below_55"
    elif (lower >= 85 and points["quiet"] >= 24 and points["sound"] >= 16
          and confidence == "high"):
        grade, reason = "A", "priority_candidate"
    elif lower >= 70 and points["quiet"] >= 21 and points["sound"] >= 12:
        grade, reason = "B", "consider"
    else:
        grade, reason = "C", "score_or_core_quality_insufficient"
    return {"community": data.get("community"), "score": lower if complete else None,
            "score_range": [lower, upper], "grade": grade, "reason": reason,
            "dimension_points": points,
            "evidence_coverage_percent": sum(WEIGHTS[k] for k in points),
            "failed_gates": failures, "unknown_gates": unknown,
            "unknown_dimensions": missing_dimensions, "warnings": warnings,
            "calculated_unit_price_yuan": round(calculated, 2) if calculated is not None else None,
            "purchase_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="property JSON path")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as handle:
            result = score(json.load(handle))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.exit(2, f"Invalid input: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
