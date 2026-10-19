import ExcelJS from "exceljs";
import { promises as fs } from "node:fs";
import path from "node:path";

export type Cell = string | number | null;
export type Sheet = { name: string; columns: string[]; rows: Cell[][] };
export type ExportResult = { xlsxPath: string; csvPaths: string[] };

/** 파일명으로 쓸 수 없는 문자와 경로 이동(..)을 `_`로 바꾼다. 비면 "export". */
export function sanitizeBaseName(name: string): string {
  const s = name
    .trim()
    .replace(/^[. ]+|[. ]+$/g, "")
    .replace(/[\/:*?"<>|\u0000-\u001f]/g, "_")
    .replace(/\.{2,}/g, "_");
  return !s || /^_+$/.test(s) ? "export" : s;
}

/** 엑셀이 수식으로 읽는 문자열(=, +, -, @, 탭, CR로 시작)은 앞에 '를 붙여 무력화한다. */
export function neutralizeFormula(v: Cell): Cell {
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(v)) return `'${v}`;
  return v;
}

function sheetTitle(name: string): string {
  const s = name.replace(/[\[\]*?:\/]/g, "_").trim().slice(0, 31);
  return s || "Sheet";
}

function csvField(v: Cell): string {
  if (v === null) return "";
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(sheet: Sheet): string {
  const lines = [sheet.columns.map((c) => csvField(neutralizeFormula(c))).join(",")];
  for (const row of sheet.rows) {
    lines.push(row.map((c) => csvField(neutralizeFormula(c))).join(","));
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}

/** 시트들을 <baseName>.xlsx 하나와 시트별 CSV(UTF-8 BOM)로 dir 아래에 저장한다. */
export async function exportSheets(
  sheets: Sheet[],
  opts: { dir: string; baseName: string }
): Promise<ExportResult> {
  const dir = path.resolve(opts.dir);
  await fs.mkdir(dir, { recursive: true });
  const base = sanitizeBaseName(opts.baseName);

  const wb = new ExcelJS.Workbook();
  const used = new Set<string>();
  for (const sheet of sheets) {
    let title = sheetTitle(sheet.name);
    for (let i = 2; used.has(title.toLowerCase()); i++) {
      title = `${title.slice(0, 28)}_${i}`;
    }
    used.add(title.toLowerCase());
    const ws = wb.addWorksheet(title);
    ws.addRow(sheet.columns.map((c) => neutralizeFormula(c)));
    for (const row of sheet.rows) ws.addRow(row.map((c) => neutralizeFormula(c)));
  }
  const xlsxPath = path.join(dir, `${base}.xlsx`);
  await wb.xlsx.writeFile(xlsxPath);

  const csvPaths: string[] = [];
  for (const sheet of sheets) {
    const p = path.join(dir, `${base}-${sanitizeBaseName(sheet.name)}.csv`);
    await fs.writeFile(p, toCsv(sheet), "utf8");
    csvPaths.push(p);
  }
  return { xlsxPath, csvPaths };
}
