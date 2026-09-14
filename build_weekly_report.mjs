import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const payload = JSON.parse(await fs.readFile("output/reduktor40-report.json", "utf8"));
const workbook = Workbook.create();
const report = workbook.worksheets.add("Отчёт");
const campaigns = workbook.worksheets.add("Кампании");
const raw = workbook.worksheets.add("Исходные данные");
workbook.comments.setSelf({ displayName: "User" });

const periodBlocks = [
  ["Текущая неделя", payload.latest_week],
  ["Предыдущая неделя", payload.previous_week],
  ["Месяц на дату", payload.month_to_date],
];
const rawRows = [[
  "Период", "Диапазон", "Ключ", "Название", "Расход", "Показы", "Клики", "Заявки",
  "Целевые", "Нецелевые", "Необработанные", "Неклассифицированные",
]];
const rawIndex = new Map();
for (const [periodName, block] of periodBlocks) {
  for (const [key, row] of Object.entries(block.rows)) {
    rawRows.push([
      periodName, block.period, key, payload.labels[key] ?? (key === "account" ? "ИТОГО" : key),
      row.spend, row.impressions, row.clicks, row.leads, row.target_leads, row.non_target_leads,
      row.unprocessed_leads, row.unclassified_leads,
    ]);
    rawIndex.set(`${periodName}|${key}`, rawRows.length);
  }
}
raw.getRange(`A1:L${rawRows.length}`).values = rawRows;
raw.tables.add(`A1:L${rawRows.length}`, true, "SourceDataTable");
raw.freezePanes.freezeRows(1);
raw.showGridLines = false;
raw.getRange("A1:L1").format = { fill: "#0B5A8E", font: { bold: true, color: "#FFFFFF" } };
raw.getRange(`E2:E${rawRows.length}`).format.numberFormat = '#,##0.00 "₽"';
raw.getRange(`F2:L${rawRows.length}`).format.numberFormat = "#,##0";
raw.getRange(`A1:L${rawRows.length}`).format.autofitColumns();
raw.getRange("A:A").format.columnWidth = 18;
raw.getRange("B:B").format.columnWidth = 24;
raw.getRange("C:C").format.columnWidth = 24;
raw.getRange("D:D").format.columnWidth = 34;

const currentRaw = rawIndex.get("Текущая неделя|account");
const previousRaw = rawIndex.get("Предыдущая неделя|account");
const mtdRaw = rawIndex.get("Месяц на дату|account");
const source = (row, col) => `'Исходные данные'!${col}${row}`;

report.showGridLines = false;
report.getRange("A1:E1").merge();
report.getRange("A1").values = [[`${payload.project} — еженедельный мониторинг`]];
report.getRange("A1:E1").format = { fill: "#0B5A8E", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center" };
report.getRange("A2:E2").merge();
report.getRange("A2").values = [[`${payload.latest_week.period} vs ${payload.previous_week.period}`]];
report.getRange("A2:E2").format = { fill: "#D9EAF5", font: { bold: true, color: "#123B56" }, horizontalAlignment: "center" };
report.getRange("A4:D4").values = [["Показатель", "Текущая неделя", "Предыдущая неделя", "Изменение"]];
report.getRange("A4:D4").format = { fill: "#17699B", font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };

const metricRows = [
  ["Расход", "E", "currency"], ["Показы", "F", "integer"], ["Клики", "G", "integer"],
  ["CTR", null, "percent"], ["CPC", null, "currency"], ["Заявки Roistat", "H", "integer"],
  ["CPA", null, "currency"], ["CR", null, "percent"], ["Целевые заявки", "I", "integer"],
  ["CPA целевой заявки", null, "currency"], ["% целевых", null, "percent"],
];
const formulasFor = (rawRow) => ({
  "Расход": `=${source(rawRow, "E")}`,
  "Показы": `=${source(rawRow, "F")}`,
  "Клики": `=${source(rawRow, "G")}`,
  "CTR": `=IFERROR(${source(rawRow, "G")}/${source(rawRow, "F")},0)`,
  "CPC": `=IFERROR(${source(rawRow, "E")}/${source(rawRow, "G")},0)`,
  "Заявки Roistat": `=${source(rawRow, "H")}`,
  "CPA": `=IFERROR(${source(rawRow, "E")}/${source(rawRow, "H")},0)`,
  "CR": `=IFERROR(${source(rawRow, "H")}/${source(rawRow, "G")},0)`,
  "Целевые заявки": `=${source(rawRow, "I")}`,
  "CPA целевой заявки": `=IFERROR(${source(rawRow, "E")}/${source(rawRow, "I")},0)`,
  "% целевых": `=IFERROR(${source(rawRow, "I")}/${source(rawRow, "H")},0)`,
});
const currentFormulas = formulasFor(currentRaw);
const previousFormulas = formulasFor(previousRaw);
metricRows.forEach(([label, , kind], index) => {
  const row = 5 + index;
  report.getRange(`A${row}`).values = [[label]];
  report.getRange(`B${row}`).formulas = [[currentFormulas[label]]];
  report.getRange(`C${row}`).formulas = [[previousFormulas[label]]];
  report.getRange(`D${row}`).formulas = [[`=IFERROR(B${row}/C${row}-1,0)`]];
  const format = kind === "currency" ? '#,##0 "₽"' : kind === "percent" ? "0.0%" : "#,##0";
  report.getRange(`B${row}:C${row}`).format.numberFormat = format;
  report.getRange(`D${row}`).format.numberFormat = "0.0%";
});
report.getRange("A5:D15").format.borders = { preset: "inside", style: "thin", color: "#D7E0E5" };
const yellow = { fill: "#FFF2CC", font: { color: "#9C6500" } };
const green = { fill: "#E2F0D9", font: { color: "#375623" } };
const red = { fill: "#FCE4D6", font: { color: "#9C0006" } };
for (const row of [9, 10, 11, 12, 13, 14, 15]) {
  const cell = report.getRange(`D${row}`);
  cell.conditionalFormats.add("cellIs", { operator: "between", formula: [-0.15, -0.10], format: yellow });
  cell.conditionalFormats.add("cellIs", { operator: "between", formula: [0.10, 0.15], format: yellow });
}
for (const row of [10, 12, 13, 15]) {
  report.getRange(`D${row}`).conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0.15, format: green });
  report.getRange(`D${row}`).conditionalFormats.add("cellIs", { operator: "lessThan", formula: -0.15, format: red });
}
for (const row of [9, 11, 14]) {
  report.getRange(`D${row}`).conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0.15, format: red });
  report.getRange(`D${row}`).conditionalFormats.add("cellIs", { operator: "lessThan", formula: -0.15, format: green });
}

report.getRange("A17:D17").merge();
report.getRange("A17").values = [["Комментарий"]];
report.getRange("A17:D17").format = { fill: "#17699B", font: { bold: true, color: "#FFFFFF" } };
const diag = payload.diagnostics;
const commentary = diag.human_comment;
report.getRange("A18:D22").merge();
report.getRange("A18").values = [[commentary]];
report.getRange("A18:D22").format = { fill: diag.quality_preliminary ? "#FFF2CC" : "#E2F0D9", wrapText: true, verticalAlignment: "top", font: { color: "#303030" } };

report.getRange("A24:E24").merge();
report.getRange("A24").values = [["План/факт сентября на 02.09.2026"]];
report.getRange("A24:E24").format = { fill: "#17699B", font: { bold: true, color: "#FFFFFF" } };
report.getRange("A25:E25").values = [["Показатель", "План месяца", "План на дату", "Факт", "Отклонение к плану на дату"]];
report.getRange("A25:E25").format = { fill: "#D9EAF5", font: { bold: true, color: "#123B56" }, wrapText: true };
const planRows = [
  ["Расход", "spend", "E", "currency"], ["Клики", "clicks", "G", "integer"],
  ["Заявки", "leads", "H", "integer"], ["CPC", "cpc", null, "currency"],
  ["CR", "cr", null, "percent"], ["CPA", "cpa", null, "currency"],
];
planRows.forEach(([label, key, rawCol, kind], index) => {
  const row = 26 + index;
  report.getRange(`A${row}`).values = [[label]];
  report.getRange(`B${row}:C${row}`).values = [[payload.month_plan[key], payload.plan_to_date[key]]];
  let factFormula;
  if (rawCol) factFormula = `=${source(mtdRaw, rawCol)}`;
  else if (key === "cpc") factFormula = `=IFERROR(${source(mtdRaw, "E")}/${source(mtdRaw, "G")},0)`;
  else if (key === "cr") factFormula = `=IFERROR(${source(mtdRaw, "H")}/${source(mtdRaw, "G")},0)`;
  else factFormula = `=IFERROR(${source(mtdRaw, "E")}/${source(mtdRaw, "H")},0)`;
  report.getRange(`D${row}`).formulas = [[factFormula]];
  report.getRange(`E${row}`).formulas = [[`=IFERROR(D${row}/C${row}-1,0)`]];
  const format = kind === "currency" ? '#,##0 "₽"' : kind === "percent" ? "0.0%" : "#,##0.0";
  report.getRange(`B${row}:D${row}`).format.numberFormat = format;
  report.getRange(`E${row}`).format.numberFormat = "0.0%";
});
report.getRange("A26:E31").format.borders = { preset: "inside", style: "thin", color: "#D7E0E5" };
for (const row of [28, 29, 30, 31]) {
  const cell = report.getRange(`E${row}`);
  cell.conditionalFormats.add("cellIs", { operator: "between", formula: [-0.20, -0.10], format: yellow });
  cell.conditionalFormats.add("cellIs", { operator: "between", formula: [0.10, 0.20], format: yellow });
}
for (const row of [28, 30]) {
  report.getRange(`E${row}`).conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0.20, format: green });
  report.getRange(`E${row}`).conditionalFormats.add("cellIs", { operator: "lessThan", formula: -0.20, format: red });
}
for (const row of [29, 31]) {
  report.getRange(`E${row}`).conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0.20, format: red });
  report.getRange(`E${row}`).conditionalFormats.add("cellIs", { operator: "lessThan", formula: -0.20, format: green });
}
report.getRange("E26").conditionalFormats.addCustom("=AND(E26<-20%,E28<-10%)", red);
report.getRange("E26").conditionalFormats.addCustom("=AND(E26>20%,E28<10%)", red);
report.getRange("E26").conditionalFormats.addCustom("=AND(ABS(E26)>=10%,ABS(E26)<=20%,E28<-10%)", yellow);
report.getRange("A33:E33").merge();
report.getRange("A33").values = [["Планы качества заявок отсутствуют; показатели качества представлены только по факту."]];
report.getRange("A33:E33").format = { fill: "#F2F2F2", font: { italic: true, color: "#666666" }, wrapText: true };
report.freezePanes.freezeRows(4);
report.getRange("A1:E33").format.font = { name: "Arial", size: 10 };
report.getRange("A1:A33").format.columnWidth = 30;
report.getRange("B1:D33").format.columnWidth = 20;
report.getRange("E1:E33").format.columnWidth = 22;
report.getRange("A18:D22").format.rowHeight = 34;

campaigns.showGridLines = false;
campaigns.getRange("A1:M1").merge();
campaigns.getRange("A1").values = [[`Кампании: ${payload.latest_week.period}`]];
campaigns.getRange("A1:M1").format = { fill: "#0B5A8E", font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center" };
campaigns.getRange("A3:M3").values = [["Кампания", "Расход", "Показы", "Клики", "CTR", "CPC", "Заявки", "CPA", "CR", "Целевые", "CPA целевой", "% целевых", "Качество"]];
campaigns.getRange("A3:M3").format = { fill: "#17699B", font: { bold: true, color: "#FFFFFF" }, wrapText: true, horizontalAlignment: "center" };
const currentCampaignKeys = Object.keys(payload.latest_week.rows).filter(k => k.startsWith("campaign:"));
currentCampaignKeys.sort((a, b) => (payload.labels[a] ?? a).localeCompare(payload.labels[b] ?? b, "ru"));
currentCampaignKeys.forEach((key, index) => {
  const row = 4 + index;
  const rawRow = rawIndex.get(`Текущая неделя|${key}`);
  campaigns.getRange(`A${row}`).values = [[payload.labels[key] ?? key]];
  campaigns.getRange(`B${row}:D${row}`).formulas = [[`=${source(rawRow, "E")}`, `=${source(rawRow, "F")}`, `=${source(rawRow, "G")}`]];
  campaigns.getRange(`E${row}`).formulas = [[`=IFERROR(D${row}/C${row},0)`]];
  campaigns.getRange(`F${row}`).formulas = [[`=IFERROR(B${row}/D${row},0)`]];
  campaigns.getRange(`G${row}`).formulas = [[`=${source(rawRow, "H")}`]];
  campaigns.getRange(`H${row}`).formulas = [[`=IFERROR(B${row}/G${row},0)`]];
  campaigns.getRange(`I${row}`).formulas = [[`=IFERROR(G${row}/D${row},0)`]];
  campaigns.getRange(`J${row}`).formulas = [[`=${source(rawRow, "I")}`]];
  campaigns.getRange(`K${row}`).formulas = [[`=IFERROR(B${row}/J${row},0)`]];
  campaigns.getRange(`L${row}`).formulas = [[`=IFERROR(J${row}/G${row},0)`]];
  campaigns.getRange(`M${row}`).values = [[payload.latest_week.rows[key].quality_preliminary ? "Предварительно" : "Достаточно данных"]];
});
const campaignEnd = 3 + currentCampaignKeys.length;
campaigns.tables.add(`A3:M${campaignEnd}`, true, "CampaignReportTable");
campaigns.getRange(`B4:B${campaignEnd}`).format.numberFormat = '#,##0 "₽"';
campaigns.getRange(`C4:D${campaignEnd}`).format.numberFormat = "#,##0";
campaigns.getRange(`E4:E${campaignEnd}`).format.numberFormat = "0.0%";
campaigns.getRange(`F4:F${campaignEnd}`).format.numberFormat = '#,##0 "₽"';
campaigns.getRange(`G4:G${campaignEnd}`).format.numberFormat = "#,##0";
campaigns.getRange(`H4:H${campaignEnd}`).format.numberFormat = '#,##0 "₽"';
campaigns.getRange(`I4:I${campaignEnd}`).format.numberFormat = "0.0%";
campaigns.getRange(`J4:J${campaignEnd}`).format.numberFormat = "#,##0";
campaigns.getRange(`K4:K${campaignEnd}`).format.numberFormat = '#,##0 "₽"';
campaigns.getRange(`L4:L${campaignEnd}`).format.numberFormat = "0.0%";
campaigns.getRange(`M4:M${campaignEnd}`).conditionalFormats.add("containsText", { text: "Предварительно", format: { fill: "#FFF2CC", font: { color: "#9C6500" } } });
campaigns.freezePanes.freezeRows(3);
campaigns.getRange(`A1:M${campaignEnd}`).format.font = { name: "Arial", size: 9 };
campaigns.getRange(`A1:M${campaignEnd}`).format.autofitColumns();
campaigns.getRange("A:A").format.columnWidth = 34;
campaigns.getRange("M:M").format.columnWidth = 18;

const checks = [];
checks.push((await workbook.inspect({ kind: "table", range: "Отчёт!A1:E33", include: "values,formulas", tableMaxRows: 40, tableMaxCols: 8 })).ndjson);
checks.push((await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "formula errors" })).ndjson);
console.log(checks.join("\n"));

await fs.mkdir("output/previews", { recursive: true });
for (const sheetName of ["Отчёт", "Кампании", "Исходные данные"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`output/previews/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save("output/reduktor40-weekly-2026-08-24.xlsx");
