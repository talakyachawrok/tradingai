"""Position sizing calculator using verified instrument contract specifications."""

import math
from app.core.instruments import instrument_registry, normalize_symbol
from app.models.analysis import PositionSizeRequest, PositionSizeResult


def calculate_position_size(req: PositionSizeRequest) -> PositionSizeResult:
    """
    Calculate lot/unit position size strictly from configured contract specs.
    Refuses to guess missing tick values or contract sizes.
    """
    norm = normalize_symbol(req.symbol)
    spec = instrument_registry.get(norm)
    risk_amount = round(req.account_balance * (req.risk_percentage / 100.0), 2)
    stop_distance = abs(req.entry_price - req.stop_loss)

    if stop_distance <= 0:
        return PositionSizeResult(
            symbol=norm,
            specs_available=bool(spec and spec.specs_complete),
            risk_amount=risk_amount,
            stop_distance=0.0,
            warning="Entry price and stop-loss cannot be identical.",
            details="Invalid zero stop distance.",
        )

    if (
        spec is None
        or not spec.specs_complete
        or not spec.tick_size
        or not spec.tick_value_per_lot
        or not spec.contract_size
    ):
        return PositionSizeResult(
            symbol=norm,
            specs_available=False,
            risk_amount=risk_amount,
            stop_distance=round(stop_distance, 6),
            warning=f"Instrument contract specifications for {norm} are incomplete or missing.",
            details=(
                "Position sizing refused rather than guessing contract size or tick value. "
                "Configure contract_size, tick_size, and tick_value_per_lot in Instrument Settings."
            ),
        )

    ticks_at_risk = stop_distance / spec.tick_size
    risk_per_lot = ticks_at_risk * spec.tick_value_per_lot
    if risk_per_lot <= 0:
        return PositionSizeResult(
            symbol=norm,
            specs_available=False,
            risk_amount=risk_amount,
            stop_distance=round(stop_distance, 6),
            warning="Calculated risk per lot is invalid.",
            details="Check tick_size and tick_value_per_lot configuration.",
        )

    raw_lots = risk_amount / risk_per_lot
    # Round to 8 decimals before floor to avoid IEEE-754 float precision under-allocation
    steps = math.floor(round(raw_lots / spec.lot_step, 8))
    recommended_lots = round(max(0.0, steps * spec.lot_step), 4)
    recommended_units = round(recommended_lots * spec.contract_size, 4)

    pips_or_ticks = (
        round(stop_distance / spec.pip_size, 2) if spec.pip_size else round(ticks_at_risk, 1)
    )
    warning = None
    if recommended_lots < spec.min_lot:
        warning = (
            f"Risk budget (${risk_amount:.2f}) is too small for minimum lot size ({spec.min_lot}) "
            f"at a stop distance of {stop_distance:.{spec.decimals}f}."
        )

    return PositionSizeResult(
        symbol=norm,
        specs_available=True,
        risk_amount=risk_amount,
        stop_distance=round(stop_distance, spec.decimals),
        recommended_lots=recommended_lots,
        recommended_units=recommended_units,
        pip_or_tick_risk=pips_or_ticks,
        warning=warning,
        details=(
            f"Risking {req.risk_percentage:.2f}% (${risk_amount:.2f}) over {pips_or_ticks} "
            f"{'pips' if spec.pip_size else 'ticks'} at ${spec.tick_value_per_lot}/tick per 1.0 lot."
        ),
    )
