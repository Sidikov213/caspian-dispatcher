// Экран «Игра с ботом»: партия против Stockfish с тренером — оценка хода, подсказка, угроза соперника.
import { Chessground } from 'chessground';
import type { Key } from 'chessground/types';
import { Chess } from 'chessops/chess';
import { makeSan } from 'chessops/san';
import { parseUci } from 'chessops/util';
import type { Engine, Line } from './engine';
import {
  $, GRADE_LABEL, GRADE_MARK, boardState, fenOf, fmtEval, grade, posFromFen, resultText, sanLine, sanOf,
  terminalLine, uciOf, userMove, winPct, winPctFor, type Side,
} from './shared';

const LEVELS = [
  { name: '1 — новичок', skill: 0, ms: 50 },
  { name: '2 — любитель', skill: 3, ms: 100 },
  { name: '3 — уверенный любитель', skill: 6, ms: 150 },
  { name: '4 — клубный игрок', skill: 9, ms: 200 },
  { name: '5 — сильный клубный', skill: 12, ms: 300 },
  { name: '6 — кандидат в мастера', skill: 15, ms: 500 },
  { name: '7 — мастер', skill: 18, ms: 800 },
  { name: '8 — полная сила', skill: 20, ms: 1500 },
];
const DEPTH = 12;

interface Played {
  uci: string;
  san: string;
  mark: string;
  cls: string;
}

export function initPlay(engine: Engine, openReview: (pgn: string) => void): void {
  let pos = Chess.default();
  let moves: Played[] = [];
  let side: Side = 'white';
  let session = 0;
  let hintStage = 0;
  const cache = new Map<string, Promise<Line | null>>();

  const levelSel = $<HTMLSelectElement>('play-level');
  LEVELS.forEach((l, i) => levelSel.add(new Option(l.name, String(i))));
  levelSel.value = '2';
  const sideSel = $<HTMLSelectElement>('play-side');
  const coach = $<HTMLInputElement>('play-coach');
  const bar = $('play-bar');

  const cg = Chessground($('play-board'), {
    premovable: { enabled: false },
    movable: { free: false, events: { after: onUserMove } },
    drawable: { enabled: true },
  });

  const coachOn = () => coach.checked;
  const myTurn = () => pos.turn === side && !pos.isEnd();

  function evalFen(fen: string): Promise<Line | null> {
    const end = terminalLine(posFromFen(fen));
    if (end) return Promise.resolve(end);
    let p = cache.get(fen);
    if (!p) {
      p = engine.analyse(fen, { depth: DEPTH }).then((r) => r?.lines[0] ?? null);
      cache.set(fen, p);
      p.then((line) => {
        if (!line) cache.delete(fen);
      });
    }
    return p;
  }

  function setBar(line: Line | null): void {
    bar.style.height = `${line && coachOn() ? winPct(line.cp) : 50}%`;
    bar.parentElement!.classList.toggle('flipped', side === 'black');
    $('play-eval').textContent = line && coachOn() ? `Оценка позиции: ${fmtEval(line)} (плюс — лучше у белых)` : '';
  }

  function render(): void {
    cg.set({ ...boardState(pos, myTurn() ? side : null, moves.at(-1)?.uci), orientation: side });
    cg.setAutoShapes([]);
    hintStage = 0;
    $('play-hint-text').textContent = '';
    const list = $('play-moves');
    list.replaceChildren();
    for (let i = 0; i < moves.length; i += 2) {
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = `${i / 2 + 1}.`;
      list.append(num);
      for (const m of [moves[i], moves[i + 1]]) {
        const el = document.createElement('span');
        el.className = `mv ${m?.cls ?? ''}`;
        el.textContent = m ? m.san + m.mark : '';
        list.append(el);
      }
    }
    list.scrollTop = list.scrollHeight;
    $('play-status').textContent = resultText(pos) ?? (myTurn() ? 'Ваш ход' : 'Бот думает…');
    for (const id of ['play-hint', 'play-threat']) $<HTMLButtonElement>(id).disabled = !myTurn() || !coachOn();
    $<HTMLButtonElement>('play-undo').disabled = moves.length === 0;
    $<HTMLButtonElement>('play-review').disabled = moves.length < 2;
  }

  async function next(): Promise<void> {
    const s = session;
    if (pos.isEnd()) return;
    if (pos.turn !== side) {
      const level = LEVELS[Number(levelSel.value)];
      const res = await engine.analyse(fenOf(pos), { movetime: level.ms, skill: level.skill });
      if (s !== session || !res) return;
      const move = parseUci(res.bestmove);
      if (!move || !pos.isLegal(move)) return;
      moves.push({ uci: uciOf(pos, move), san: makeSan(pos, move), mark: '', cls: '' });
      pos.play(move);
      render();
    }
    if (coachOn()) {
      const line = await evalFen(fenOf(pos));
      if (s === session) setBar(line);
    }
  }

  async function onUserMove(orig: Key, dest: Key): Promise<void> {
    const move = userMove(pos, orig, dest);
    if (!move) return render();
    const s = session;
    const fenBefore = fenOf(pos);
    const played: Played = { uci: uciOf(pos, move), san: makeSan(pos, move), mark: '', cls: '' };
    pos.play(move);
    moves.push(played);
    render();
    $('play-feedback').textContent = '';
    if (coachOn()) {
      const [before, after] = await Promise.all([evalFen(fenBefore), evalFen(fenOf(pos))]);
      if (s !== session) return;
      if (before && after) {
        const loss = Math.max(0, winPctFor(before.cp, side) - winPctFor(after.cp, side));
        const g = grade(loss, before.pv[0] === played.uci);
        played.mark = GRADE_MARK[g];
        played.cls = g;
        let html = `<b class="${g}">${played.san}${played.mark} — ${GRADE_LABEL[g].toLowerCase()}.</b>`;
        if (g !== 'best' && g !== 'good' && before.pv[0]) {
          html += ` Сильнее было ${sanOf(fenBefore, before.pv[0])} (оценка ${fmtEval(before)}), после вашего хода — ${fmtEval(after)}.`;
        }
        $('play-feedback').innerHTML = html;
        setBar(after);
        render();
      }
    }
    void next();
  }

  function restart(): void {
    engine.cancel();
    cache.clear();
    session++;
  }

  function newGame(): void {
    restart();
    side = sideSel.value as Side;
    pos = Chess.default();
    moves = [];
    $('play-feedback').textContent = '';
    setBar(null);
    render();
    void next();
  }

  function undo(): void {
    restart();
    moves.pop();
    if (moves.length % 2 !== (side === 'white' ? 0 : 1)) moves.pop();
    pos = Chess.default();
    for (const m of moves) pos.play(parseUci(m.uci)!);
    $('play-feedback').textContent = '';
    render();
    void next();
  }

  async function hint(): Promise<void> {
    const s = session;
    const fen = fenOf(pos);
    const line = await evalFen(fen);
    if (s !== session || !line?.pv[0]) return;
    const best = line.pv[0];
    hintStage = Math.min(hintStage + 1, 2);
    if (hintStage === 1) {
      cg.setAutoShapes([{ orig: best.slice(0, 2) as Key, brush: 'green' }]);
      $('play-hint-text').textContent = 'Присмотритесь к этой фигуре. Нажмите «Подсказка» ещё раз — покажу ход.';
    } else {
      cg.setAutoShapes([{ orig: best.slice(0, 2) as Key, dest: best.slice(2, 4) as Key, brush: 'green' }]);
      $('play-hint-text').textContent = `Лучший ход: ${sanOf(fen, best)}. Продолжение: ${sanLine(fen, line.pv)}.`;
    }
  }

  async function threat(): Promise<void> {
    const s = session;
    const out = $('play-hint-text');
    if (pos.isCheck()) {
      out.textContent = 'Вам шах — сначала нужно его отразить.';
      return;
    }
    // «Пропускаем» свой ход и смотрим, что сыграет соперник.
    const parts = fenOf(pos).split(' ');
    parts[1] = parts[1] === 'w' ? 'b' : 'w';
    parts[3] = '-';
    const fen = parts.join(' ');
    const res = await engine.analyse(fen, { depth: DEPTH });
    const line = res?.lines[0];
    if (s !== session || !line?.pv[0]) return;
    const m = line.pv[0];
    cg.setAutoShapes([{ orig: m.slice(0, 2) as Key, dest: m.slice(2, 4) as Key, brush: 'red' }]);
    out.textContent = `Если ничего не предпринять, соперник сыграет ${sanOf(fen, m)} (оценка станет ${fmtEval(line)}).`;
  }

  function toPgn(): string {
    const result = !pos.isEnd() ? '*' : pos.isCheckmate() ? (pos.turn === 'white' ? '0-1' : '1-0') : '1/2-1/2';
    const body = moves.map((m, i) => (i % 2 === 0 ? `${i / 2 + 1}. ${m.san}` : m.san)).join(' ');
    const [white, black] = side === 'white' ? ['Я', 'Stockfish'] : ['Stockfish', 'Я'];
    return `[White "${white}"]\n[Black "${black}"]\n[Result "${result}"]\n\n${body} ${result}\n`;
  }

  $('play-new').onclick = newGame;
  $('play-undo').onclick = undo;
  $('play-hint').onclick = () => void hint();
  $('play-threat').onclick = () => void threat();
  $('play-review').onclick = () => openReview(toPgn());
  coach.onchange = () => {
    setBar(null);
    render();
    void next();
  };
  newGame();
}
