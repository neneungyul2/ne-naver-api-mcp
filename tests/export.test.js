import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import ExcelJS from "exceljs";
import {
  sanitizeBaseName,
  neutralizeFormula,
  exportSheets,
} from "../dist/src/export/export.js";

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "exp-"));
const inside = (dir, p) => !path.relative(dir, p).startsWith("..") && !path.isAbsolute(path.relative(dir, p));

test("sanitizeBaseName은 경로 문자와 ..를 없애고 한글/공백은 보존한다", () => {
  const s = sanitizeBaseName("../../evil");
  assert.equal(/[\\/]/.test(s) || s.includes(".."), false);
  assert.equal(sanitizeBaseName("그래머 비교 2025"), "그래머 비교 2025");
  assert.equal(sanitizeBaseName("..."), "export");
  assert.equal(sanitizeBaseName(""), "export");
});

test("neutralizeFormula는 수식으로 읽힐 문자열만 무력화한다", () => {
  assert.equal(neutralizeFormula('=HYPERLINK("x")'), `'=HYPERLINK("x")`);
  assert.equal(neutralizeFormula("+1"), "'+1");
  assert.equal(neutralizeFormula("-1"), "'-1");
  assert.equal(neutralizeFormula("@SUM"), "'@SUM");
  assert.equal(neutralizeFormula("\t탭"), "'\t탭");
  assert.equal(neutralizeFormula(-3), -3);
  assert.equal(neutralizeFormula(null), null);
  assert.equal(neutralizeFormula("정상"), "정상");
});

test("exportSheets는 xlsx와 시트별 csv를 dir 안에 쓴다", async () => {
  const dir = tmp();
  const res = await exportSheets(
    [
      { name: "트렌드", columns: ["기간", "A"], rows: [["2025-01-01", 12.5], ["2025-02-01", null]] },
      { name: "한계", columns: ["문구"], rows: [["상대 지수입니다"]] },
    ],
    { dir, baseName: "비교" }
  );
  assert.ok(fs.existsSync(res.xlsxPath));
  assert.equal(res.csvPaths.length, 2);
  for (const p of [res.xlsxPath, ...res.csvPaths]) {
    assert.ok(fs.existsSync(p));
    assert.ok(inside(dir, p), p);
  }
});

test("baseName에 ../가 있어도 dir 밖에 파일이 생기지 않는다", async () => {
  const dir = tmp();
  const res = await exportSheets([{ name: "s", columns: ["a"], rows: [["x"]] }], {
    dir,
    baseName: "../x",
  });
  for (const p of [res.xlsxPath, ...res.csvPaths]) assert.ok(inside(dir, p), p);
});

test("CSV는 BOM으로 시작하고 쉼표/따옴표/개행을 이스케이프하며 한글이 보존된다", async () => {
  const dir = tmp();
  const res = await exportSheets(
    [{ name: "t", columns: ["이름", "메모"], rows: [["그래머", 'a,"b"\nc'], [null, 3]] }],
    { dir, baseName: "csv" }
  );
  const buf = fs.readFileSync(res.csvPaths[0]);
  assert.deepEqual([...buf.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  const text = buf.toString("utf8").slice(1);
  assert.ok(text.startsWith("이름,메모\r\n"));
  assert.ok(text.includes('그래머,"a,""b""\nc"'));
  assert.ok(text.includes(",3"));
});

test("xlsx를 다시 읽으면 입력과 같고 수식 시작 셀은 무력화돼 있다", async () => {
  const dir = tmp();
  const res = await exportSheets(
    [{ name: "트렌드", columns: ["기간", "값"], rows: [["2025-01-01", 12.5], ["=1+1", "정상"]] }],
    { dir, baseName: "x" }
  );
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.readFile(res.xlsxPath);
  const ws = wb.getWorksheet("트렌드");
  assert.ok(ws);
  assert.equal(ws.getRow(1).getCell(1).value, "기간");
  assert.equal(ws.getRow(2).getCell(2).value, 12.5);
  assert.equal(ws.getRow(3).getCell(1).value, "'=1+1");
});

test("시트 이름이 길거나 금지 문자가 있어도 31자 이내로 정리된다", async () => {
  const dir = tmp();
  const long = "가".repeat(40) + "[x]";
  const res = await exportSheets([{ name: long, columns: ["a"], rows: [["x"]] }], { dir, baseName: "long" });
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.readFile(res.xlsxPath);
  const name = wb.worksheets[0].name;
  assert.ok(name.length <= 31);
  assert.equal(/[\[\]\*\?:\\\/]/.test(name), false);
});
