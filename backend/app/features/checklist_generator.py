def build_checklist(protocol: dict) -> dict:
    d = (protocol.get("sections") or {}).get("diagnostics", {})
    items = []
    for key, label in [("complaints","Жалобы"),("anamnesis","Анамнез"),("physical_exam","Осмотр"),
                       ("lab_tests","Лабораторно"),("instrumental_tests","Инструментально")]:
        v = d.get(key, [])
        items.append({"block": label, "points": v if v else [f"Проверить по разделу: {label} (см. протокол)"]})
    raw = d.get("raw","")
    if raw and all(not x["points"] or "см. протокол" in x["points"][0] for x in items):
        # нарезка сырого текста в пункты
        lines = [l.strip(" -•\t") for l in raw.split("\n") if len(l.strip()) > 10][:15]
        if lines: items.append({"block": "Из протокола", "points": lines})
    return {"nosology": protocol.get("nosology"), "title": protocol.get("title"), "checklist": items}
