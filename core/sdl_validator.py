# core/sdl_validator.py
# Purpose: Validate SDL strategy dictionaries against the canonical schema and emit structured errors.
# API's: ValidationError, validate_strategy_dict
# Notes: Used by core.strategy_loader; does not perform any file I/O.

from dataclasses import dataclass
from typing import Any, Dict, List

from core.sdl_schema import (
    STRATEGY_REQUIRED_FIELDS,
    VALID_CONDITION_TYPES,
    VALID_DIRECTIONS,
    VALID_REGIMES,
    VALID_SIZING,
    VALID_TIMEFRAMES,
    VALID_MTF_ROLES,
)


@dataclass
class ValidationError:
    """Structured validation error for SDL strategy definitions.

    Attributes:
        path: JSON-style path to the offending field (e.g. "entry.conditions[0].type").
        message: Human-readable description of the problem.
        severity: Currently always "error"; warnings can be added later in Phase F.
    """

    path: str
    message: str
    severity: str = "error"


def _add_error(errors: List[ValidationError], path: str, message: str) -> None:
    """Append a new error to the list with severity='error'."""

    errors.append(ValidationError(path=path, message=message, severity="error"))


def _validate_conditions_block(
    errors: List[ValidationError],
    name: str,
    conditions: Any,
    base_path: str,
) -> None:
    """Validate a list of condition dicts using the canonical condition schema.

    This is shared between entry, exit.signal_exit, and MTF condition blocks.
    """

    if not isinstance(conditions, list):
        _add_error(
            errors,
            base_path,
            f"Strategy '{name}': {base_path} must be list",
        )
        return

    for idx, cond in enumerate(conditions):
        ctype = cond.get("type")
        path = f"{base_path}[{idx}].type"
        if ctype not in VALID_CONDITION_TYPES:
            _add_error(
                errors,
                path,
                f"Strategy '{name}': invalid condition type '{ctype}'",
            )
            continue

        # Only ema_cross has extra hard requirements at the schema level. Other
        # types either have sensible defaults or are validated at runtime.
        if ctype == "ema_cross":
            if "fast" not in cond or "slow" not in cond:
                _add_error(
                    errors,
                    f"{base_path}[{idx}]",
                    f"Strategy '{name}': ema_cross requires fast and slow periods",
                )


def validate_strategy_dict(name: str, data: Dict[str, Any]) -> List[ValidationError]:
    """Validate a single strategy dictionary.

    This mirrors the legacy inline validation logic from core.strategy_loader,
    but emits structured ValidationError objects instead of raising directly.
    It has been extended in Phase F to understand optional 'mtf' sections, but
    these remain schema-only hooks until Phase I wires them into execution.

    Args:
        name: Strategy key (usually the lower-cased filename stem).
        data: Parsed JSON strategy dictionary.

    Returns:
        A list of ValidationError objects. If the list is empty, the strategy
        is considered valid for the current SDL version.
    """

    errors: List[ValidationError] = []

    # --- Required top-level fields ---
    for field in STRATEGY_REQUIRED_FIELDS:
        if field not in data:
            _add_error(errors, field, f"Strategy '{name}': missing '{field}'")

    # If core fields are missing, further checks will likely cascade; bail out
    # early to keep error output readable.
    if errors:
        return errors

    # --- Regime & direction ---
    regime = data.get("regime")
    if regime not in VALID_REGIMES:
        _add_error(
            errors,
            "regime",
            f"Strategy '{name}': invalid regime '{regime}'. Must be one of {VALID_REGIMES}",
        )

    direction = data.get("direction")
    if direction not in VALID_DIRECTIONS:
        _add_error(errors, "direction", f"Strategy '{name}': invalid direction")

    # --- Entry / exit structure ---
    entry = data.get("entry", {})
    conditions = entry.get("conditions")
    if not isinstance(conditions, list):
        _add_error(
            errors,
            "entry.conditions",
            f"Strategy '{name}': entry.conditions must be list",
        )

    exit_block = data.get("exit", {})
    if "stop_loss" not in exit_block:
        _add_error(
            errors,
            "exit.stop_loss",
            f"Strategy '{name}': exit.stop_loss required",
        )

    # --- Risk sizing ---
    risk = data.get("risk", {})
    sizing = risk.get("sizing")
    if sizing not in VALID_SIZING:
        _add_error(
            errors,
            "risk.sizing",
            f"Strategy '{name}': invalid sizing '{sizing}'",
        )
    else:
        if sizing == "atr" and "atr_multiplier" not in risk:
            _add_error(
                errors,
                "risk.atr_multiplier",
                f"Strategy '{name}': atr sizing requires atr_multiplier",
            )
        if sizing == "fixed_usd" and "max_exposure_usd" not in risk:
            _add_error(
                errors,
                "risk.max_exposure_usd",
                f"Strategy '{name}': fixed_usd requires max_exposure_usd",
            )
        if sizing == "equity_pct" and "risk_per_trade_pct" not in risk:
            _add_error(
                errors,
                "risk.risk_per_trade_pct",
                f"Strategy '{name}': equity_pct requires risk_per_trade_pct",
            )

    # --- Conditions (entry) ---
    if isinstance(conditions, list):
        _validate_conditions_block(
            errors=errors,
            name=name,
            conditions=conditions,
            base_path="entry.conditions",
        )

    # --- Conditions (exit.signal_exit) ---
    signal_exit = exit_block.get("signal_exit", [])
    if isinstance(signal_exit, list):
        _validate_conditions_block(
            errors=errors,
            name=name,
            conditions=signal_exit,
            base_path="exit.signal_exit",
        )

    # --- Optional MTF section ---
    mtf = data.get("mtf")
    if mtf is not None:
        if not isinstance(mtf, dict):
            _add_error(errors, "mtf", f"Strategy '{name}': mtf must be an object if present")
        else:
            higher = mtf.get("higher_timeframes", [])
            if not isinstance(higher, list):
                _add_error(
                    errors,
                    "mtf.higher_timeframes",
                    f"Strategy '{name}': mtf.higher_timeframes must be list if present",
                )
            else:
                for idx, block in enumerate(higher):
                    path_base = f"mtf.higher_timeframes[{idx}]"
                    if not isinstance(block, dict):
                        _add_error(
                            errors,
                            path_base,
                            f"Strategy '{name}': each mtf.higher_timeframes entry must be an object",
                        )
                        continue

                    tf = block.get("timeframe")
                    if tf not in VALID_TIMEFRAMES:
                        _add_error(
                            errors,
                            f"{path_base}.timeframe",
                            f"Strategy '{name}': invalid mtf timeframe '{tf}'. Must be one of {VALID_TIMEFRAMES}",
                        )

                    role = block.get("role")
                    if role is not None and role not in VALID_MTF_ROLES:
                        _add_error(
                            errors,
                            f"{path_base}.role",
                            f"Strategy '{name}': invalid mtf role '{role}'. Must be one of {VALID_MTF_ROLES}",
                        )

                    mtf_conditions = block.get("conditions")
                    if mtf_conditions is not None:
                        _validate_conditions_block(
                            errors=errors,
                            name=name,
                            conditions=mtf_conditions,
                            base_path=f"{path_base}.conditions",
                        )

    return errors
# core/sdl_validator.py v0.4 (240 lines)
