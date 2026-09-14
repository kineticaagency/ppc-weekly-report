from __future__ import annotations

from dataclasses import asdict

from .models import Metrics


def pct_change(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def significance(change: float | None) -> str:
    if change is None:
        return "insufficient_data"
    magnitude = abs(change)
    if magnitude < 0.10:
        return "normal"
    if magnitude <= 0.15:
        return "attention"
    return "diagnostic"


def _pct(value: float | None) -> str:
    return "н/д" if value is None else f"{value:+.1%}"


def _magnitude(value: float | None) -> str:
    return "н/д" if value is None else f"{abs(value):.1%}"


def _human_pct(value: float | None, *, absolute: bool = False) -> str:
    if value is None:
        return "н/д"
    number = abs(value) if absolute else value
    return f"{number:.1%}".replace(".", ",")


def _segment_contribution(current: Metrics, previous: Metrics, use_cr: bool) -> float:
    if use_cr:
        current_cr = current.derived()["cr"]
        previous_cr = previous.derived()["cr"]
        if current_cr is not None and previous_cr is not None:
            return current.clicks * (current_cr - previous_cr)
    return current.leads - previous.leads


def _traffic_detail(
    current_rows: dict[str, Metrics], previous_rows: dict[str, Metrics], labels: dict[str, str],
    campaign_networks: dict[str, str], use_cr: bool,
) -> str | None:
    account_current = current_rows["account"]
    account_previous = previous_rows["account"]
    account_contribution = _segment_contribution(account_current, account_previous, use_cr)
    candidates = []
    for key in ("network:search", "network:context"):
        current, previous = current_rows.get(key, Metrics()), previous_rows.get(key, Metrics())
        contribution = _segment_contribution(current, previous, use_cr)
        changes = {
            "leads": pct_change(current.leads, previous.leads),
            "cr": pct_change(current.derived()["cr"], previous.derived()["cr"]),
            "cpa": pct_change(current.derived()["cpa"], previous.derived()["cpa"]),
        }
        useful = any(value is not None and abs(value) > 0.15 for value in changes.values())
        if account_contribution:
            useful = useful or abs(contribution) >= 0.30 * abs(account_contribution)
        if useful and (current.clicks >= 20 or previous.clicks >= 20):
            relative_strength = max(abs(value) for value in changes.values() if value is not None)
            sample_size = max(current.clicks, previous.clicks)
            candidates.append((abs(contribution), relative_strength, sample_size, key, current, previous, changes))
    if not candidates:
        return None
    _, _, _, network_key, current, previous, changes = max(candidates)
    label = labels.get(network_key, network_key)
    verb = "внесла" if network_key == "network:context" else "внёс"
    sentence = (
        f"Наибольший вклад {verb} {label}: заявки {'выросли' if current.leads > previous.leads else 'снизились'} "
        f"с {previous.leads} до {current.leads}"
    )
    if changes["cr"] is not None and abs(changes["cr"]) > 0.15:
        sentence += f" при {'росте' if changes['cr'] > 0 else 'снижении'} CR на {_human_pct(changes['cr'], absolute=True)}"

    campaign_candidates = []
    for key, mapped_network in campaign_networks.items():
        if mapped_network != network_key:
            continue
        campaign_current = current_rows.get(key, Metrics())
        campaign_previous = previous_rows.get(key, Metrics())
        contribution = _segment_contribution(campaign_current, campaign_previous, use_cr)
        lead_change = pct_change(campaign_current.leads, campaign_previous.leads)
        if lead_change is not None and abs(lead_change) > 0.15 and (campaign_current.clicks >= 20 or campaign_previous.clicks >= 20):
            sample_size = max(campaign_current.clicks, campaign_previous.clicks)
            campaign_candidates.append((abs(contribution), abs(lead_change), sample_size, key, campaign_current, campaign_previous))
    if campaign_candidates:
        _, _, _, campaign_key, campaign_current, campaign_previous = max(campaign_candidates)
        campaign_delta = campaign_current.leads - campaign_previous.leads
        network_delta = current.leads - previous.leads
        if not network_delta or abs(campaign_delta) >= 0.30 * abs(network_delta):
            sentence += f"; основное изменение пришлось на кампанию «{labels.get(campaign_key, campaign_key)}»"
    return sentence + "."


def _human_comment(
    current: Metrics, previous: Metrics, changes: dict[str, float | None], preliminary: bool,
    current_rows: dict[str, Metrics] | None = None, previous_rows: dict[str, Metrics] | None = None,
    labels: dict[str, str] | None = None, campaign_networks: dict[str, str] | None = None,
) -> str:
    cpa, leads = changes["cpa"], changes["leads"]
    cpc, cr, spend = changes["cpc"], changes["cr"], changes["spend"]
    sentences: list[str] = []

    if cpa is None:
        result = "Динамику CPA пока нельзя корректно оценить"
    elif significance(cpa) == "normal":
        result = f"CPA изменился на {_human_pct(cpa, absolute=True)} и остался в пределах нормальной динамики"
    else:
        result = f"CPA {'вырос' if cpa > 0 else 'снизился'} на {_human_pct(cpa, absolute=True)}"
    if leads is not None and abs(leads) >= 0.10:
        result += f", количество заявок {'увеличилось' if leads > 0 else 'сократилось'} на {_human_pct(leads, absolute=True)}"
    sentences.append(result + ".")

    drivers = [(name, value) for name, value in (("CPC", cpc), ("CR", cr)) if value is not None and abs(value) >= 0.10]
    if cpa is not None and significance(cpa) != "normal" and drivers:
        def supports_cpa_change(driver: tuple[str, float]) -> bool:
            name, value = driver
            effect = value if name == "CPC" else -value
            return effect * cpa > 0

        supporting = [driver for driver in drivers if supports_cpa_change(driver)]
        opposing = [driver for driver in drivers if not supports_cpa_change(driver)]
        name, value = max(supporting or drivers, key=lambda item: abs(item[1]))
        direction = "рост" if value > 0 else "снижение"
        reason = f"Основной причиной {'стал' if direction == 'рост' else 'стало'} {direction} {name} на {_human_pct(value, absolute=True)}"
        if opposing:
            other_name, other_value = max(opposing, key=lambda item: abs(item[1]))
            other_direction = "рост" if other_value > 0 else "снижение"
            cpa_direction = "рост" if cpa > 0 else "снижение"
            reason += (
                f"; {other_direction} {other_name} на {_human_pct(other_value, absolute=True)} "
                f"частично сдержало {cpa_direction} стоимости заявки"
            )
        sentences.append(reason + ".")

    current_derived, previous_derived = current.derived(), previous.derived()
    target_share_change = changes["target_share"]
    target_cpa_change = changes["target_cpa"]
    if current_derived["target_share"] is not None and previous_derived["target_share"] is not None:
        share_direction = "выросла" if target_share_change and target_share_change > 0 else (
            "снизилась" if target_share_change and target_share_change < 0 else "не изменилась"
        )
        quality = (
            f"Доля целевых заявок {share_direction} "
            f"с {_human_pct(previous_derived['target_share'])} до {_human_pct(current_derived['target_share'])}"
        )
        if current_derived["target_cpa"] is not None and previous_derived["target_cpa"] is not None:
            cpa_direction = "вырос" if target_cpa_change and target_cpa_change > 0 else (
                "снизился" if target_cpa_change and target_cpa_change < 0 else "не изменился"
            )
            previous_target_cpa = f"{previous_derived['target_cpa']:,.0f}".replace(",", " ")
            current_target_cpa = f"{current_derived['target_cpa']:,.0f}".replace(",", " ")
            quality += (
                f", а CPA целевой заявки {cpa_direction} "
                f"с {previous_target_cpa} до {current_target_cpa} ₽"
            )
        if not preliminary and target_share_change is not None and target_cpa_change is not None:
            if target_share_change > 0 and target_cpa_change < 0:
                quality += " — качество трафика улучшилось"
            elif target_share_change < 0 and target_cpa_change > 0:
                quality += " — качество трафика ухудшилось"
        sentences.append(quality + ".")

    needs_traffic_detail = any(
        changes[key] is not None and abs(changes[key]) > 0.15 for key in ("cpa", "cr", "leads")
    )
    if needs_traffic_detail and current_rows and previous_rows:
        use_cr = cr is not None and abs(cr) > 0.15
        detail = _traffic_detail(current_rows, previous_rows, labels or {}, campaign_networks or {}, use_cr)
        if detail:
            sentences.append(detail)
    if preliminary:
        share = current.derived()["unprocessed_share"] or 0
        sentences.append(
            f"Качество трафика пока рано оценивать — {_human_pct(share)} заявок за период ещё не обработано в Roistat."
        )
    return " ".join(sentences)


def analyze(
    current: Metrics, previous: Metrics, preliminary_threshold: float,
    current_rows: dict[str, Metrics] | None = None, previous_rows: dict[str, Metrics] | None = None,
    labels: dict[str, str] | None = None, campaign_networks: dict[str, str] | None = None,
) -> dict:
    current_all = {**asdict(current), **current.derived()}
    previous_all = {**asdict(previous), **previous.derived()}
    changes = {key: pct_change(value, previous_all[key]) for key, value in current_all.items()}
    cpa_change = changes["cpa"]
    confirmed: list[str] = []
    hypotheses: list[str] = []
    notices: list[str] = []

    if significance(cpa_change) == "normal":
        confirmed.append(f"CPA изменился на {_pct(cpa_change)} — в пределах нормальной динамики.")
    else:
        if changes["cpc"] is not None and abs(changes["cpc"]) >= 0.10:
            direction = "рост" if changes["cpc"] > 0 else "снижение"
            effect = "росту" if changes["cpc"] > 0 else "снижению"
            confirmed.append(f"{direction.capitalize()} CPC на {_magnitude(changes['cpc'])} способствовало {effect} CPA.")
        if changes["cr"] is not None and abs(changes["cr"]) >= 0.10:
            direction = "рост" if changes["cr"] > 0 else "снижение"
            effect = "снижению" if changes["cr"] > 0 else "росту"
            confirmed.append(f"{direction.capitalize()} CR на {_magnitude(changes['cr'])} способствовало {effect} CPA.")
        if not confirmed:
            hypotheses.append("Изменение CPA требует проверки кампаний: крупных подтверждённых драйверов CPC/CR не найдено.")

    confirmed.append(
        f"Расход {_pct(changes['spend'])}, клики {_pct(changes['clicks'])}, заявки {_pct(changes['leads'])}."
    )
    unprocessed_share = current_all["unprocessed_share"] or 0
    preliminary = unprocessed_share >= preliminary_threshold
    if preliminary:
        notices.append(
            f"Не обработано {current.unprocessed_leads} из {current.leads} заявок ({unprocessed_share:.1%}); "
            "качество трафика предварительное."
        )
    if current.unclassified_leads:
        notices.append(f"Не классифицировано по утверждённой карте статусов: {current.unclassified_leads} заявок.")
    return {
        "changes": changes,
        "significance": {key: significance(value) for key, value in changes.items()},
        "confirmed": confirmed,
        "hypotheses": hypotheses,
        "notices": notices,
        "quality_preliminary": preliminary,
        "human_comment": _human_comment(
            current, previous, changes, preliminary, current_rows, previous_rows, labels, campaign_networks
        ),
    }
