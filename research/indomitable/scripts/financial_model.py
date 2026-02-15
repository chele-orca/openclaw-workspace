#!/usr/bin/env python3
"""
Deterministic financial model for E&P companies.
All arithmetic lives here. Claude never computes these values.

Usage:
    from financial_model import EPModel

    model = EPModel(params)
    print(model.revenue())
    print(model.funding_gap())

    expectations = model.generate_expectations("Q4 2025")
    results = model.score_actuals(expectations, actuals)
"""


class EPModel:
    """Simple E&P financial model. Rough but explicit."""

    def __init__(self, params: dict):
        """
        params keys (all from financial_claims / extracted_metrics / external data):
          production_volume     - total production (Bcf or Bcfe)
          production_unit       - 'Bcf', 'Bcfe'
          realized_price        - $/Mcf or $/Mcfe
          price_unit            - '$/Mcf', '$/Mcfe'
          operating_cost_per_unit - LOE + gathering per Mcfe
          capex_low             - capital expenditure low end (M)
          capex_high            - capital expenditure high end (M)
          hedge_volume          - hedged volume (Bcf)
          hedge_price           - hedge price ($/Mcf or $/MMBtu)
          forward_curve_price   - from external data ($/MMBtu)
          prior_capex           - prior period capex for YoY comparison (M)
          prior_production      - prior period production for YoY comparison
          operating_cash_flow   - OCF from filing (M) — used as-is when available
        """
        self.p = params

    def _get(self, key, default=None):
        """Get a parameter, returning default if missing or None."""
        val = self.p.get(key)
        return val if val is not None else default

    def _capex_low(self):
        return self._get('capex_low')

    def _capex_high(self):
        return self._get('capex_high', self._get('capex_low'))

    def _capex_mid(self):
        low = self._capex_low()
        high = self._capex_high()
        if low is not None and high is not None:
            return (low + high) / 2
        return low or high

    def _production(self):
        """Production in Bcf/Bcfe."""
        return self._get('production_volume')

    def revenue(self):
        """production (Bcf) * realized_price ($/Mcf) = $M.
        Unit math: Bcf * $/Mcf = 10^9 cf * $ / 10^3 cf = 10^6 * $ = $M."""
        prod = self._production()
        price = self._get('realized_price')
        if prod is not None and price is not None:
            return round(prod * price)  # Bcf * $/Mcf = $M directly
        return None

    def hedged_revenue(self):
        """hedge_volume (Bcf) * hedge_price ($/Mcf) = $M."""
        vol = self._get('hedge_volume')
        price = self._get('hedge_price')
        if vol is not None and price is not None:
            return round(vol * price)
        return None

    def unhedged_volume(self):
        """production - hedge_volume (Bcf)."""
        prod = self._production()
        hedge = self._get('hedge_volume')
        if prod is not None and hedge is not None:
            return round(prod - hedge, 1)
        return None

    def unhedged_revenue(self, price=None):
        """(production - hedge_volume) * price = $M.
        Uses forward_curve_price if price not specified."""
        vol = self.unhedged_volume()
        if vol is None:
            return None
        price = price or self._get('forward_curve_price') or self._get('realized_price')
        if price is not None:
            return round(vol * price)
        return None

    def operating_cash_flow(self):
        """Return OCF. Prefer reported OCF; else compute revenue - (production * opex)."""
        ocf = self._get('operating_cash_flow')
        if ocf is not None:
            return ocf

        rev = self.revenue()
        prod = self._production()
        opex = self._get('operating_cost_per_unit')
        if rev is not None and prod is not None and opex is not None:
            total_opex = round(prod * opex)  # Bcf * $/Mcf = $M
            return rev - total_opex
        return None

    def funding_gap(self):
        """capex - OCF (range-aware). Returns dict with low/high or None."""
        ocf = self.operating_cash_flow()
        capex_low = self._capex_low()
        capex_high = self._capex_high()
        if ocf is not None and capex_low is not None:
            gap_low = round(capex_low - ocf)
            gap_high = round((capex_high or capex_low) - ocf)
            return {
                'low': min(gap_low, gap_high),
                'high': max(gap_low, gap_high),
                'unit': 'M',
            }
        return None

    def breakeven_price(self):
        """Price at which OCF = capex midpoint.
        breakeven = capex_mid * realized_price / OCF."""
        capex_mid = self._capex_mid()
        ocf = self.operating_cash_flow()
        realized = self._get('realized_price')
        if capex_mid and ocf and realized and ocf > 0:
            return round(capex_mid * realized / ocf, 2)
        return None

    def hedge_coverage_pct(self):
        """hedge_volume / production * 100."""
        hedge = self._get('hedge_volume')
        prod = self._production()
        if hedge is not None and prod is not None and prod > 0:
            return round((hedge / prod) * 100, 1)
        return None

    def capex_change_pct(self):
        """(capex_mid - prior_capex) / prior_capex * 100."""
        capex_mid = self._capex_mid()
        prior = self._get('prior_capex')
        if capex_mid is not None and prior is not None and prior > 0:
            return round(((capex_mid - prior) / prior) * 100, 1)
        return None

    def production_change_pct(self):
        """(production - prior_production) / prior_production * 100."""
        prod = self._production()
        prior = self._get('prior_production')
        if prod is not None and prior is not None and prior > 0:
            return round(((prod - prior) / prior) * 100, 1)
        return None

    def forward_curve_upside(self):
        """(forward_curve_price - realized_price) * unhedged_volume = $M."""
        fwd = self._get('forward_curve_price')
        realized = self._get('realized_price')
        vol = self.unhedged_volume()
        if fwd is not None and realized is not None and vol is not None:
            return round((fwd - realized) * vol)  # Bcf * $/Mcf = $M
        return None

    def net_debt_to_ocf(self):
        """Net debt / OCF — leverage proxy (turns of OCF to repay debt)."""
        nd = self._get('net_debt')
        ocf = self.operating_cash_flow()
        if nd is not None and ocf is not None and ocf > 0:
            return round(nd / ocf, 1)
        return None

    def interest_coverage(self):
        """OCF / annual interest expense — ability to service debt from operations."""
        ocf = self.operating_cash_flow()
        interest = self._get('interest_expense')
        if ocf is not None and interest is not None and interest > 0:
            return round(ocf / interest, 1)
        return None

    def debt_service_capacity(self):
        """(OCF - maintenance capex) / interest expense.
        Maintenance capex estimated as 40% of total capex if not provided."""
        ocf = self.operating_cash_flow()
        interest = self._get('interest_expense')
        if ocf is None or interest is None or interest <= 0:
            return None
        maint_capex = self._get('maintenance_capex')
        if maint_capex is None:
            # Estimate maintenance capex as 40% of midpoint capex
            capex_mid = self._capex_mid()
            if capex_mid is not None:
                maint_capex = capex_mid * 0.4
            else:
                return None
        return round((ocf - maint_capex) / interest, 1)

    def funding_gap_coverage(self):
        """Analyze how the funding gap could be covered.
        Returns dict with gap amount and coverage sources."""
        gap = self.funding_gap()
        if gap is None or gap['high'] <= 0:
            return None  # No gap to cover

        ocf = self.operating_cash_flow()
        result = {
            'gap_low': gap['low'],
            'gap_high': gap['high'],
            'unit': 'M',
        }

        # Credit facility availability
        facility = self._get('credit_facility_available')
        if facility is not None:
            result['credit_facility_available'] = facility
            result['facility_covers_gap_pct'] = round((facility / gap['high']) * 100, 1) if gap['high'] > 0 else None

        # Interest burden
        interest = self._get('interest_expense')
        if interest is not None:
            result['annual_interest_expense'] = interest
            total_debt = self._get('total_long_term_debt') or self._get('net_debt')
            if total_debt and total_debt > 0:
                result['implied_interest_rate_pct'] = round((interest / total_debt) * 100, 1)

        # Debt maturity
        maturity = self._get('debt_maturity_next')
        if maturity is not None:
            result['next_maturity'] = maturity

        return result

    def ocf_coverage_pct(self):
        """OCF / capex midpoint * 100 — how much of capex is internally funded."""
        ocf = self.operating_cash_flow()
        capex_mid = self._capex_mid()
        if ocf is not None and capex_mid is not None and capex_mid > 0:
            return round((ocf / capex_mid) * 100, 1)
        return None

    def free_cash_flow(self):
        """OCF - capex (range-aware). Inverse of funding gap sign."""
        gap = self.funding_gap()
        if gap:
            return {
                'low': -gap['high'],
                'high': -gap['low'],
                'unit': 'M',
            }
        return None

    def compute_derived_claims(self, claims: dict) -> dict:
        """
        Compute derived financial metrics and add them to claims dict.
        This replaces the standalone compute_derived_claims() from generate_thesis.py.
        Modifies claims in-place and returns it.
        """
        if not claims:
            return claims

        gap = self.funding_gap()
        if gap:
            claims['funding_gap'] = {
                'low': gap['low'],
                'high': gap['high'],
                'unit': 'M',
                'methodology': 'capex_guidance minus operating_cash_flow',
                'source': 'derived',
            }

        pct = self.capex_change_pct()
        if pct is not None:
            prior = self._get('prior_capex')
            claims['capex_increase_pct'] = {
                'value': pct,
                'unit': '%',
                'baseline': f"{prior}M (prior period)",
                'source': 'derived',
            }

        coverage = self.hedge_coverage_pct()
        if coverage is not None:
            claims['hedge_coverage_pct'] = {
                'value': coverage,
                'unit': '%',
                'source': 'derived',
            }

        brk = self.breakeven_price()
        if brk is not None and 'breakeven_price' not in claims:
            claims['breakeven_price'] = {
                'value': brk,
                'unit': self._get('price_unit', '$/Mcfe'),
                'basis': 'self-funding at capex guidance',
                'source': 'derived',
            }

        leverage = self.net_debt_to_ocf()
        if leverage is not None:
            claims['net_debt_to_ocf'] = {
                'value': leverage,
                'unit': 'x',
                'basis': 'net_debt / operating_cash_flow',
                'source': 'derived',
            }

        coverage = self.ocf_coverage_pct()
        if coverage is not None:
            claims['ocf_coverage_pct'] = {
                'value': coverage,
                'unit': '%',
                'basis': 'operating_cash_flow / capex_midpoint',
                'source': 'derived',
            }

        ic = self.interest_coverage()
        if ic is not None:
            claims['interest_coverage'] = {
                'value': ic,
                'unit': 'x',
                'basis': 'operating_cash_flow / interest_expense',
                'source': 'derived',
            }

        dsc = self.debt_service_capacity()
        if dsc is not None:
            claims['debt_service_capacity'] = {
                'value': dsc,
                'unit': 'x',
                'basis': '(OCF - maintenance_capex) / interest_expense',
                'source': 'derived',
            }

        fgc = self.funding_gap_coverage()
        if fgc is not None:
            claims['funding_gap_coverage'] = {
                'value': fgc,
                'unit': 'composite',
                'source': 'derived',
            }

        return claims

    def generate_expectations(self, period: str) -> list:
        """
        Generate quantitative expectations for next earnings period.
        Returns list of dicts with:
          metric_name, expected_low, expected_mid, expected_high,
          expected_unit, assumption_basis
        """
        expectations = []

        # Revenue expectation
        prod = self._production()
        price = self._get('realized_price')
        fwd = self._get('forward_curve_price')
        if prod is not None and price is not None:
            # Quarterly: divide annual by 4 as baseline
            # Use price range: realized as low, forward curve as high
            price_low = price
            price_high = fwd if fwd and fwd > price else price * 1.1
            rev_low = round(prod * price_low / 4)  # Bcf * $/Mcf / 4 = quarterly $M
            rev_high = round(prod * price_high / 4)
            rev_mid = round((rev_low + rev_high) / 2)
            expectations.append({
                'metric_name': 'revenue',
                'expected_low': rev_low,
                'expected_mid': rev_mid,
                'expected_high': rev_high,
                'expected_unit': 'M',
                'assumption_basis': f"{round(prod/4)} Bcf production at ${price_low:.2f}-${price_high:.2f} realized",
            })

        # OCF expectation
        ocf = self.operating_cash_flow()
        if ocf is not None:
            # Quarterly OCF ~ annual / 4 with margin
            ocf_mid = round(ocf / 4)
            ocf_low = round(ocf_mid * 0.9)
            ocf_high = round(ocf_mid * 1.1)
            expectations.append({
                'metric_name': 'operating_cash_flow',
                'expected_low': ocf_low,
                'expected_mid': ocf_mid,
                'expected_high': ocf_high,
                'expected_unit': 'M',
                'assumption_basis': f"${ocf}M annual OCF prorated quarterly",
            })

        # Capex expectation
        capex_low = self._capex_low()
        capex_high = self._capex_high()
        if capex_low is not None:
            q_low = round(capex_low / 4)
            q_high = round((capex_high or capex_low) / 4)
            q_mid = round((q_low + q_high) / 2)
            expectations.append({
                'metric_name': 'capex',
                'expected_low': q_low,
                'expected_mid': q_mid,
                'expected_high': q_high,
                'expected_unit': 'M',
                'assumption_basis': f"${capex_low}-${capex_high}M annual guidance prorated",
            })

        # Production expectation
        if prod is not None:
            q_prod = round(prod / 4, 1)
            prod_low = round(q_prod * 0.97, 1)
            prod_high = round(q_prod * 1.03, 1)
            unit = self._get('production_unit', 'Bcf')
            expectations.append({
                'metric_name': 'production_volume',
                'expected_low': prod_low,
                'expected_mid': q_prod,
                'expected_high': prod_high,
                'expected_unit': unit,
                'assumption_basis': f"{prod} {unit} annual guidance prorated, +/-3%",
            })

        # Free cash flow / funding gap
        gap = self.funding_gap()
        if gap:
            q_gap_low = round(gap['low'] / 4)
            q_gap_high = round(gap['high'] / 4)
            q_gap_mid = round((q_gap_low + q_gap_high) / 2)
            expectations.append({
                'metric_name': 'funding_gap',
                'expected_low': q_gap_low,
                'expected_mid': q_gap_mid,
                'expected_high': q_gap_high,
                'expected_unit': 'M',
                'assumption_basis': f"${gap['low']}-${gap['high']}M annual gap prorated",
            })

        return expectations

    def score_actuals(self, expectations: list, actuals: dict) -> list:
        """
        Compare actuals to expectations.
        actuals: dict of {metric_name: actual_value}

        Returns list of dicts with:
          metric_name, expected_mid, actual_value, vs_expected_pct,
          within_range, thesis_impact
        """
        results = []
        for exp in expectations:
            name = exp['metric_name']
            actual = actuals.get(name)
            if actual is None:
                continue

            expected_mid = exp.get('expected_mid')
            expected_low = exp.get('expected_low')
            expected_high = exp.get('expected_high')

            vs_pct = None
            if expected_mid and expected_mid != 0:
                vs_pct = round(((actual - expected_mid) / abs(expected_mid)) * 100, 2)

            within_range = (
                expected_low is not None and
                expected_high is not None and
                expected_low <= actual <= expected_high
            )

            # Determine thesis impact
            if within_range:
                impact = 'confirms'
            elif vs_pct is not None and abs(vs_pct) > 15:
                impact = 'breaks' if abs(vs_pct) > 25 else 'challenges'
            elif vs_pct is not None and abs(vs_pct) > 5:
                impact = 'challenges'
            else:
                impact = 'neutral'

            results.append({
                'metric_name': name,
                'expected_mid': expected_mid,
                'expected_low': expected_low,
                'expected_high': expected_high,
                'actual_value': actual,
                'vs_expected_pct': vs_pct,
                'within_range': within_range,
                'thesis_impact': impact,
            })

        return results

    def check_kill_criteria(self, criteria: list, actuals: dict) -> list:
        """
        Check kill criteria against actuals.
        criteria: list of dicts with metric_name, threshold_value, threshold_operator
        actuals: dict of {metric_name: actual_value}

        Returns list of dicts with criterion info + triggered flag.
        """
        ops = {
            '>': lambda a, t: a > t,
            '<': lambda a, t: a < t,
            '>=': lambda a, t: a >= t,
            '<=': lambda a, t: a <= t,
            '!=': lambda a, t: a != t,
            '=': lambda a, t: a == t,
        }

        results = []
        for c in criteria:
            name = c.get('metric_name')
            threshold = c.get('threshold_value')
            operator = c.get('threshold_operator', '>')
            actual = actuals.get(name) if name else None

            triggered = False
            if actual is not None and threshold is not None:
                op_fn = ops.get(operator)
                if op_fn:
                    triggered = op_fn(float(actual), float(threshold))

            results.append({
                'criterion_id': c.get('id'),
                'criterion': c.get('criterion'),
                'metric_name': name,
                'threshold_value': threshold,
                'threshold_operator': operator,
                'actual_value': actual,
                'triggered': triggered,
            })

        return results

    def summary(self) -> dict:
        """Return a summary of all computed values for display/logging."""
        return {
            'revenue': self.revenue(),
            'hedged_revenue': self.hedged_revenue(),
            'unhedged_volume': self.unhedged_volume(),
            'unhedged_revenue': self.unhedged_revenue(),
            'operating_cash_flow': self.operating_cash_flow(),
            'funding_gap': self.funding_gap(),
            'free_cash_flow': self.free_cash_flow(),
            'breakeven_price': self.breakeven_price(),
            'hedge_coverage_pct': self.hedge_coverage_pct(),
            'capex_change_pct': self.capex_change_pct(),
            'production_change_pct': self.production_change_pct(),
            'forward_curve_upside': self.forward_curve_upside(),
            'net_debt_to_ocf': self.net_debt_to_ocf(),
            'ocf_coverage_pct': self.ocf_coverage_pct(),
            'interest_coverage': self.interest_coverage(),
            'debt_service_capacity': self.debt_service_capacity(),
            'funding_gap_coverage': self.funding_gap_coverage(),
        }

    @staticmethod
    def params_from_claims(claims: dict, external_context: dict = None) -> dict:
        """
        Build model params dict from financial_claims JSONB and external context.
        This is the bridge between DB storage and model input.
        """
        params = {}
        if not claims:
            return params

        def _val(claim_name, key='value'):
            c = claims.get(claim_name, {})
            return c.get(key) if isinstance(c, dict) else None

        params['production_volume'] = _val('production_volume')
        params['production_unit'] = claims.get('production_volume', {}).get('unit', 'Bcfe')
        params['realized_price'] = _val('realized_price')
        params['price_unit'] = claims.get('realized_price', {}).get('unit', '$/Mcfe')
        params['operating_cost_per_unit'] = _val('operating_cost_per_unit')
        params['capex_low'] = _val('capex_guidance', 'low') or _val('capex_guidance')
        params['capex_high'] = _val('capex_guidance', 'high') or _val('capex_guidance')
        params['hedge_volume'] = _val('hedge_volume')
        params['hedge_price'] = claims.get('hedge_volume', {}).get('price') or _val('hedge_price')
        params['prior_capex'] = _val('prior_capex')
        params['prior_production'] = _val('prior_production')
        params['operating_cash_flow'] = _val('operating_cash_flow')
        params['net_debt'] = _val('net_debt')
        params['interest_expense'] = _val('interest_expense')
        params['credit_facility_available'] = _val('credit_facility_available')
        params['debt_maturity_next'] = _val('debt_maturity_next')
        params['total_long_term_debt'] = _val('total_long_term_debt')
        params['maintenance_capex'] = _val('maintenance_capex')

        # External context
        if external_context:
            # Prefer strip average over single-point forward
            strip = external_context.get('strip_averages', {})
            if strip.get('strip_12m'):
                params['forward_curve_price'] = strip['strip_12m']
                params['winter_strip'] = strip.get('winter_strip')
                params['summer_strip'] = strip.get('summer_strip')
                params['strip_24m'] = strip.get('strip_24m')
            else:
                # Fall back to single futures point
                commodity = external_context.get('commodity_prices', {})
                futures = commodity.get('futures', {})
                for key in ['12_month', '12m', 'cal_2026', 'cal_2027']:
                    if key in futures:
                        params['forward_curve_price'] = futures[key].get('price') or futures[key].get('value')
                        break
                if not params.get('forward_curve_price'):
                    spot = commodity.get('spot_price', {})
                    if isinstance(spot, dict):
                        params['forward_curve_price'] = spot.get('price') or spot.get('value')
                    elif isinstance(spot, (int, float)):
                        params['forward_curve_price'] = spot

        # Filter out None values
        return {k: v for k, v in params.items() if v is not None}
