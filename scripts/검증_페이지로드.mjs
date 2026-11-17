// 월배당 트래커 — 커밋 전 "페이지가 실제로 뜨는지" 검증 (의존성 없음, Node 22+)
// 사용: cd github/montly-div && node scripts/검증_페이지로드.mjs [index.html 경로] [--no-browser]
// 배경: 2026-11-12 RAW 배열 마지막 줄 끝 쉼표 누락 → `[..]\n[..]`가 문법 오류가 아니라 속성 접근으로 읽혀
//       RAW.map에서 TypeError, 표 전체가 안 그려짐. `node --check`로는 안 잡히므로 실제로 평가·로드해서 본다.
// 1단계(필수): RAW·const 데이터 블록을 JS로 평가해 구조 점검.  2단계: 헤드리스 Chrome/Edge로 로드해 콘솔 오류 0·표 행 수 > 0.
// 종료코드 0 = 통과, 1 = 실패(커밋·push 금지). 브라우저가 없으면 2단계는 건너뛰고 경고만(1단계 결과로 판정).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import vm from "node:vm";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const noBrowser = args.includes("--no-browser");
const htmlPath = path.resolve(args.find((a) => !a.startsWith("--")) || path.join(ROOT, "index.html"));
const html = fs.readFileSync(htmlPath, "utf-8");

const errors = [];
const warns = [];
const fail = (m) => errors.push(m);
const warn = (m) => warns.push(m);
const lineOf = (text, idx) => text.slice(0, idx).split("\n").length;

// ── 1단계: 인라인 스크립트의 const 리터럴을 실제 JS로 평가 ─────────────────────────────
// 리터럴의 끝을 괄호 짝으로 찾는다(문자열·주석 안의 괄호는 무시).
function literalEnd(src, start) {
  const open = src[start], close = open === "[" ? "]" : "}";
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    const c = src[i];
    if (c === '"' || c === "'" || c === "`") {
      for (i++; i < src.length && src[i] !== c; i++) if (src[i] === "\\") i++;
    } else if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
    } else if (c === "/" && src[i + 1] === "*") {
      i = src.indexOf("*/", i + 2);
      if (i < 0) return -1;
      i++;
    } else if (c === "[" || c === "{") depth++;
    else if (c === "]" || c === "}") if (--depth === 0) return src[i] === close ? i : -1;
  }
  return -1;
}

function grabConst(name) {
  const m = new RegExp(`^const ${name}\\s*=\\s*([\\[{])`, "m").exec(html);
  if (!m) return null;
  const start = m.index + m[0].length - 1;
  const end = literalEnd(html, start);
  if (end < 0) return { name, error: "닫는 괄호를 못 찾음(괄호 짝 불일치)" };
  const text = html.slice(start, end + 1);
  try {
    return { name, text, start, value: vm.runInNewContext("(" + text + ")", {}, { timeout: 5000 }) };
  } catch (e) {
    return { name, text, start, error: "평가 실패: " + e.message };
  }
}

const HEADERS = grabConst("HEADERS");
const RAW = grabConst("RAW");
if (!HEADERS?.value) fail("HEADERS 배열을 못 읽음: " + (HEADERS?.error || "없음"));
if (!RAW) fail("const RAW 를 index.html에서 못 찾음");
else if (RAW.error) fail("RAW " + RAW.error);

let rawCodes = new Set();
if (RAW?.value && HEADERS?.value) {
  const rows = RAW.value, nCol = HEADERS.value.length, iCode = HEADERS.value.indexOf("code");
  const iNm = HEADERS.value.indexOf("nm"), iDt = HEADERS.value.indexOf("dt");
  if (!Array.isArray(rows) || rows.length === 0) fail("RAW가 비어 있거나 배열이 아님");
  else {
    // (a) 텍스트 검사: 행 줄이 `]`로 끝났는데 다음 줄이 `[`로 시작 → 쉼표 누락(오류 위치를 줄 번호로 알려 줌)
    const lines = RAW.text.split("\n"), base = lineOf(html, RAW.start);
    for (let i = 0; i < lines.length - 1; i++) {
      const a = lines[i].trimEnd(), b = lines[i + 1].trimStart();
      if (/^\[/.test(a.trimStart()) && /\]$/.test(a) && /^\[/.test(b) && !/^\[\s*$/.test(a))
        fail(`RAW ${base + i}줄 끝에 쉼표 없음 → 다음 줄(${base + i + 1})과 이어져 속성 접근으로 해석됨`);
    }
    // (b) 평가 결과 검사
    const textRows = lines.filter((l) => /^\s*\["/.test(l)).length;
    if (textRows !== rows.length) fail(`RAW 행 수 불일치: 텍스트상 ${textRows}줄 ≠ 평가 결과 ${rows.length}개`);
    rows.forEach((r, i) => {
      if (!Array.isArray(r)) return fail(`RAW[${i}] 가 배열이 아님(${r === undefined ? "undefined" : typeof r}) — 앞 줄 쉼표 누락 의심`);
      if (r.length !== nCol) fail(`RAW[${i}] ${r[iCode]} 열 수 ${r.length} ≠ HEADERS ${nCol}`);
      if (typeof r[iCode] !== "string" || !r[iCode]) fail(`RAW[${i}] 코드가 문자열이 아님`);
      if (typeof r[iNm] !== "string" || !r[iNm]) fail(`RAW[${i}] ${r[iCode]} 종목명이 비어 있음`);
      if (!["월중", "월말"].includes(r[iDt])) fail(`RAW[${i}] ${r[iCode]} dt가 월중/월말이 아님: ${JSON.stringify(r[iDt])}`);
    });
    const seen = new Map();
    rows.forEach((r, i) => {
      if (!Array.isArray(r)) return;
      if (seen.has(r[iCode])) fail(`RAW 코드 중복 ${r[iCode]} (RAW[${seen.get(r[iCode])}], RAW[${i}])`);
      seen.set(r[iCode], i);
    });
    rawCodes = new Set(seen.keys());
    console.log(`RAW: ${rows.length}행 / 열 ${nCol} / 코드 ${rawCodes.size}종`);
  }
}

// 같은 방식으로 이어붙이는 코드 키 데이터 블록: 평가 가능한 객체이고 비어 있지 않아야 한다.
const BLOCKS = ["PRICE_UPDATES", "NEW_LISTINGS", "CURRENT_MARKET_CAP", "MID_DISC_CLOSE", "END_DISC_CLOSE",
  "DIVIDEND_UPDATES", "DIVIDEND_UPDATES_MERGE", "ETF_DIST_OVERRIDE", "AX12_ESTIMATED", "MACRO_DATA", "ETF_NOTICES", "NOTICE_KINDS"];
for (const name of BLOCKS) {
  const b = grabConst(name);
  if (!b) continue; // 이 버전에 없는 블록은 건너뜀
  if (b.error) { fail(`${name} ${b.error}`); continue; }
  const v = b.value;
  if (!v || typeof v !== "object" || Array.isArray(v) || !Object.keys(v).length) { fail(`${name}가 비어 있거나 객체가 아님`); continue; }
  const keys = Object.keys(v);
  if (rawCodes.size && /^(PRICE_UPDATES|CURRENT_MARKET_CAP|MID_DISC_CLOSE|END_DISC_CLOSE|DIVIDEND_UPDATES_MERGE|ETF_DIST_OVERRIDE)$/.test(name)) {
    const orphan = keys.filter((k) => !rawCodes.has(k));
    if (orphan.length) warn(`${name}: RAW에 없는 코드 ${orphan.length}개 (${orphan.slice(0, 5).join(",")}${orphan.length > 5 ? "…" : ""})`);
  }
  if (name === "PRICE_UPDATES" && rawCodes.size) {
    const miss = [...rawCodes].filter((c) => !(c in v));
    if (miss.length) warn(`PRICE_UPDATES에 없는 RAW 코드 ${miss.length}개 (${miss.slice(0, 5).join(",")}${miss.length > 5 ? "…" : ""})`);
  }
}

// ── 2단계: 헤드리스 브라우저로 실제 로드 (콘솔 오류 0 · 표 행 수 > 0) ──────────────────────
function findBrowser() {
  const c = [process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].filter(Boolean);
  return c.find((p) => fs.existsSync(p));
}

const MIME = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml" };
function serve() {
  const srv = http.createServer((req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (p === "/" || p === "/index.html") { res.writeHead(200, { "content-type": MIME[".html"] }); return res.end(html); }
    if (p === "/favicon.ico") { res.writeHead(204); return res.end(); } // 브라우저가 자동 요청 — 오류로 세지 않음
    const f = path.join(ROOT, p);
    if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": MIME[path.extname(f)] || "application/octet-stream" });
    fs.createReadStream(f).pipe(res);
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok(srv)));
}

async function browserCheck() {
  const exe = findBrowser();
  if (!exe) return warn("Chrome/Edge를 못 찾아 브라우저 로드 검증을 건너뜀 (CHROME_PATH 환경변수로 지정 가능)");
  const srv = await serve();
  const origin = `http://127.0.0.1:${srv.address().port}`;
  const udd = fs.mkdtempSync(path.join(os.tmpdir(), "mdv-chk-"));
  const proc = spawn(exe, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${udd}`, "--no-first-run",
    "--no-default-browser-check", "--disable-gpu", "--disable-extensions", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  try {
    const wsUrl = await new Promise((ok, no) => {
      let buf = "";
      const t = setTimeout(() => no(new Error("브라우저 시작 시간 초과")), 20000);
      proc.stderr.on("data", (d) => { buf += d; const m = /DevTools listening on (ws:\/\/\S+)/.exec(buf); if (m) { clearTimeout(t); ok(m[1]); } });
      proc.on("exit", () => no(new Error("브라우저가 바로 종료됨")));
    });
    const port = new URL(wsUrl).port;
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find((t) => t.type === "page");
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = () => no(new Error("CDP 연결 실패")); });
    let id = 0; const pending = new Map(); const pageErrs = [], netErrs = [];
    const send = (method, params = {}) => new Promise((ok) => { pending.set(++id, ok); ws.send(JSON.stringify({ id, method, params })); });
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result ?? m.error); pending.delete(m.id); return; }
      if (m.method === "Runtime.exceptionThrown") {
        const d = m.params.exceptionDetails;
        pageErrs.push(`${d.exception?.description?.split("\n")[0] || d.text} (줄 ${d.lineNumber + 1})`);
      } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
        pageErrs.push("console.error: " + m.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200));
      else if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
        const e = m.params.entry, local = (e.url || "").startsWith(origin);
        (local ? pageErrs : netErrs).push(`${e.text}${e.url ? " " + e.url : ""}`.slice(0, 200));
      }
    };
    await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");
    await send("Page.navigate", { url: origin + "/index.html" });
    let rows = 0;
    for (let i = 0; i < 40; i++) { // 최대 ~20초: 표가 그려지길 기다림
      await new Promise((r) => setTimeout(r, 500));
      const r = await send("Runtime.evaluate", { expression: "document.querySelectorAll('#tbody tr').length", returnByValue: true });
      rows = r?.result?.value ?? 0;
      if (rows > 0 && i >= 4) break; // 로드 후 비동기 fetch 오류도 잡히도록 최소 2초는 둠
    }
    await new Promise((r) => setTimeout(r, 1000));
    ws.close();
    pageErrs.forEach((e) => fail("브라우저 콘솔 오류: " + e));
    netErrs.forEach((e) => warn("외부 자원 로드 오류(CDN 등): " + e));
    if (rows <= 0) fail("표(#tbody)에 행이 0개 — 페이지가 안 그려짐");
    console.log(`브라우저 로드: 표 행 ${rows}개 / 콘솔 오류 ${pageErrs.length}건`);
    if (rawCodes.size && rows > 0 && rows < rawCodes.size * 0.5) warn(`표 행 ${rows}개가 RAW ${rawCodes.size}종의 절반 미만 (기본 필터 때문일 수 있음)`);
  } catch (e) {
    fail("브라우저 검증 실패: " + e.message);
  } finally {
    proc.kill(); srv.close();
    await new Promise((r) => setTimeout(r, 500));
    try { fs.rmSync(udd, { recursive: true, force: true }); } catch {}
  }
}

if (!noBrowser) await browserCheck();
else warn("--no-browser: 브라우저 로드 검증 생략");

console.log("=".repeat(60));
warns.forEach((w) => console.log("⚠ " + w));
if (errors.length) {
  errors.slice(0, 30).forEach((e) => console.log("❌ " + e));
  if (errors.length > 30) console.log(`❌ … 외 ${errors.length - 30}건`);
  console.log("→ ❌ 페이지 로드 검증 실패. 커밋·push 하지 말고 보고할 것.");
  process.exit(1);
}
console.log("✅ 페이지 로드 검증 통과 (RAW 구조·데이터 블록 평가" + (noBrowser ? "" : "·브라우저 로드") + ")");
