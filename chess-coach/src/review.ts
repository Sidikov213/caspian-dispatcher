// Экран «Разбор партии»: оценка каждого хода, график, объяснение ошибок и тренировка на них.
import { Chessground } from 'chessground';
import type { DrawShape } from 'chessground/draw';
import type { Key } from 'chessground/types';
import { parsePgn, startingPosition } from 'chessops/pgn';
import { makeSan, parseSan } from 'chessops/san';
import type { Engine, Line } from './engine';
import {
  $, GRADE_LABEL, GRADE_MARK, boardState, fenOf, fmtEval, grade, posFromFen, sanLine, sanOf, terminalLine,
  uciOf, userMove, winPct, winPctFor, type Grade, type Side,
} from './shared';

const DEPTH = 12;
const SVG = 'http://www.w3.org/2000/svg';

interface Ply {
  fen: string; // позиция перед ходом
  uci: string;
  san: string;
  side: Side;
  num: number;
  grade: Grade;
  loss: number;
}

export function initReview(engine: Engine): { load(pgn: string): void } {
  let plies: Ply[] = [];
  let lines: Line[][] = []; // lines[i] — варианты движка в позиции перед ходом i; последний — конечная позиция
  let current = 0;
  let orientation: Side = 'white';
  let run = 0;
  let training: { list: number[]; at: number; solved: boolean } | null = null;

  const cg = Chessground($('review-board'), {
    premovable: { enabled: false },
    movable: { free: false, events: { after: onTrainMove } },
    drawable: { enabled: true },
  });
  const pgnBox = $<HTMLTextAreaElement>('review-pgn');
  const arrow = (uci: string, brush: string): DrawShape => ({
    orig: uci.slice(0, 2) as Key,
    dest: uci.slice(2, 4) as Key,
    brush,
  });

  function stage(name: 'input' | 'progress' | 'result'): void {
    $('review-input').classList.toggle('hidden', name !== 'input');
    $('review-progress').classList.toggle('hidden', name !== 'progress');
    $('review-result').classList.toggle('hidden', name !== 'result');
  }

  async function analyse(pgn: string): Promise<void> {
    const err = $('review-error');
    err.textContent = '';
    const game = parsePgn(pgn)[0];
    const start = game && startingPosition(game.headers);
    if (!game || !start || start.isErr) {
      err.textContent = 'Не удалось прочитать партию. Нужен текст в формате PGN.';
      return;
    }
    const pos = start.unwrap();
    const parsed: Ply[] = [];
    for (const node of game.moves.mainline()) {
      const move = parseSan(pos, node.san);
      if (!move) {
        err.textContent = `Не удалось прочитать ход ${pos.fullmoves}${pos.turn === 'white' ? '.' : '…'} ${node.san}.`;
        return;
      }
      parsed.push({
        fen: fenOf(pos), uci: uciOf(pos, move), san: makeSan(pos, move), side: pos.turn, num: pos.fullmoves,
        grade: 'good', loss: 0,
      });
      pos.play(move);
    }
    if (parsed.length === 0) {
      err.textContent = 'В партии нет ходов.';
      return;
    }
    engine.cancel();
    const id = ++run;
    training = null;
    stage('progress');
    const fens = [...parsed.map((p) => p.fen), fenOf(pos)];
    const found: Line[][] = [];
    for (let i = 0; i < fens.length; i++) {
      $('review-progress-bar').style.width = `${(i / fens.length) * 100}%`;
      $('review-progress-text').textContent = `Разбираю позицию ${i + 1} из ${fens.length}…`;
      const end = terminalLine(posFromFen(fens[i]));
      const res = end ? [end] : (await engine.analyse(fens[i], { depth: DEPTH, multipv: 2 }))?.lines;
      if (id !== run) return;
      if (!res?.length) {
        stage('input');
        err.textContent = 'Разбор прерван. Нажмите «Разобрать» ещё раз.';
        return;
      }
      found.push(res);
    }
    parsed.forEach((p, i) => {
      const before = found[i][0];
      p.loss = Math.max(0, winPctFor(before.cp, p.side) - winPctFor(found[i + 1][0].cp, p.side));
      p.grade = grade(p.loss, before.pv[0] === p.uci);
    });
    plies = parsed;
    lines = found;
    stage('result');
    renderSummary();
    renderGraph();
    const firstBad = plies.findIndex((p) => p.grade === 'blunder' || p.grade === 'mistake');
    select(firstBad >= 0 ? firstBad : 0);
  }

  function renderSummary(): void {
    const box = $('review-summary');
    box.replaceChildren();
    const cell = (text: string, cls = '') => {
      const el = document.createElement('span');
      el.className = cls;
      el.textContent = text;
      box.append(el);
    };
    ['', 'Точность', 'Неточности', 'Ошибки', 'Зевки'].forEach((h) => cell(h, 'head'));
    for (const side of ['white', 'black'] as const) {
      const mine = plies.filter((p) => p.side === side);
      // Точность хода по потере шансов — формула Lichess.
      const acc = mine.reduce((sum, p) => sum + Math.min(100, Math.max(0, 103.1668 * Math.exp(-0.04354 * p.loss) - 3.1669)), 0);
      const count = (g: Grade) => String(mine.filter((p) => p.grade === g).length);
      cell(side === 'white' ? 'Белые' : 'Чёрные');
      cell(mine.length ? `${Math.round(acc / mine.length)}%` : '—');
      cell(count('inaccuracy'), 'mv inaccuracy');
      cell(count('mistake'), 'mv mistake');
      cell(count('blunder'), 'mv blunder');
    }
  }

  function renderGraph(): void {
    const svg = $('review-graph');
    svg.replaceChildren();
    const n = lines.length - 1;
    const x = (i: number) => (n ? (i / n) * 400 : 0);
    const y = (i: number) => 80 - (winPct(lines[i][0].cp) / 100) * 80;
    const area = document.createElementNS(SVG, 'polygon');
    area.setAttribute('points', `0,80 ${lines.map((_, i) => `${x(i)},${y(i)}`).join(' ')} 400,80`);
    area.setAttribute('fill', '#eeeae0');
    svg.append(area);
    const mid = document.createElementNS(SVG, 'line');
    for (const [k, v] of [['x1', '0'], ['x2', '400'], ['y1', '40'], ['y2', '40'], ['stroke', '#888'], ['stroke-width', '0.5']]) mid.setAttribute(k, v);
    svg.append(mid);
    const cursor = document.createElementNS(SVG, 'line');
    cursor.id = 'review-cursor';
    for (const [k, v] of [['y1', '0'], ['y2', '80'], ['stroke', '#6aa84f'], ['stroke-width', '1.5']]) cursor.setAttribute(k, v);
    svg.append(cursor);
    plies.forEach((p, i) => {
      if (p.grade !== 'blunder' && p.grade !== 'mistake') return;
      const dot = document.createElementNS(SVG, 'circle');
      dot.setAttribute('cx', String(x(i + 1)));
      dot.setAttribute('cy', String(y(i + 1)));
      dot.setAttribute('r', '2.5');
      dot.setAttribute('fill', p.grade === 'blunder' ? '#d9534f' : '#e0a030');
      svg.append(dot);
    });
    svg.onclick = (ev) => {
      const box = svg.getBoundingClientRect();
      select(Math.round(((ev.clientX - box.left) / box.width) * n) - 1);
    };
  }

  function renderMoves(): void {
    const list = $('review-moves');
    list.replaceChildren();
    const blank = () => list.append(document.createElement('span'));
    plies.forEach((p, i) => {
      if (p.side === 'white' || i === 0) {
        const num = document.createElement('span');
        num.className = 'num';
        num.textContent = `${p.num}.`;
        list.append(num);
        if (p.side === 'black') blank();
      }
      const el = document.createElement('span');
      el.className = `mv click ${p.grade}${i === current ? ' current' : ''}`;
      el.textContent = p.san + GRADE_MARK[p.grade];
      el.onclick = () => select(i);
      list.append(el);
    });
    list.querySelector('.current')?.scrollIntoView({ block: 'nearest' });
  }

  function setBar(line: Line): void {
    $('review-bar').style.height = `${winPct(line.cp)}%`;
    $('review-bar').parentElement!.classList.toggle('flipped', orientation === 'black');
  }

  /** Показывает позицию перед ходом i: красная стрелка — ход из партии, зелёная — лучший. */
  function select(i: number): void {
    if (training || plies.length === 0) return;
    current = Math.max(0, Math.min(plies.length - 1, i));
    const p = plies[current];
    const before = lines[current][0];
    const after = lines[current + 1][0];
    const best = before.pv[0];
    cg.set({ ...boardState(posFromFen(p.fen), null), orientation });
    cg.setAutoShapes(best && best !== p.uci ? [arrow(p.uci, 'red'), arrow(best, 'green')] : [arrow(p.uci, 'green')]);
    setBar(after);
    const title = `${p.num}${p.side === 'white' ? '.' : '…'} ${p.san}${GRADE_MARK[p.grade]}`;
    let html = `<b class="${p.grade}">${title} — ${GRADE_LABEL[p.grade].toLowerCase()}.</b> Оценка: ${fmtEval(before)} → ${fmtEval(after)}.`;
    if (p.grade === 'best') html += ' Это первый выбор движка.';
    else if (best) html += ` Сильнее было ${sanOf(p.fen, best)}: ${sanLine(p.fen, before.pv)}.`;
    $('review-note').innerHTML = html;
    $('review-cursor').setAttribute('x1', String(((current + 1) / (lines.length - 1)) * 400));
    $('review-cursor').setAttribute('x2', String(((current + 1) / (lines.length - 1)) * 400));
    renderMoves();
  }

  function startTraining(side: Side): void {
    let list = plies.flatMap((p, i) => (p.side === side && (p.grade === 'blunder' || p.grade === 'mistake') ? [i] : []));
    if (list.length === 0) list = plies.flatMap((p, i) => (p.side === side && p.grade === 'inaccuracy' ? [i] : []));
    if (list.length === 0) {
      $('review-note').textContent = `У ${side === 'white' ? 'белых' : 'чёрных'} в этой партии нет ошибок — тренировать нечего.`;
      return;
    }
    training = { list, at: 0, solved: false };
    orientation = side;
    $('train-start').classList.add('hidden');
    $('train-controls').classList.remove('hidden');
    showTask();
  }

  function showTask(): void {
    if (!training) return;
    const p = plies[training.list[training.at]];
    training.solved = false;
    current = training.list[training.at];
    cg.set({ ...boardState(posFromFen(p.fen), p.side), orientation });
    cg.setAutoShapes([]);
    setBar(lines[current][0]);
    $('review-note').textContent = `Задача ${training.at + 1} из ${training.list.length}. Ход ${p.num}: в партии здесь была ошибка. Найдите ход сильнее.`;
    renderMoves();
  }

  function onTrainMove(orig: Key, dest: Key): void {
    if (!training || training.solved) return;
    const i = training.list[training.at];
    const p = plies[i];
    const pos = posFromFen(p.fen);
    const move = userMove(pos, orig, dest);
    const uci = move && uciOf(pos, move);
    const top = lines[i][0];
    const match = lines[i].find((l) => l.pv[0] === uci && winPctFor(top.cp, p.side) - winPctFor(l.cp, p.side) < 5);
    const note = $('review-note');
    if (match && uci) {
      training.solved = true;
      pos.play(move);
      cg.set(boardState(pos, null, uci));
      note.innerHTML = `<b class="best">Верно: ${sanOf(p.fen, uci)}.</b> Продолжение: ${sanLine(p.fen, match.pv)}.`;
      return;
    }
    cg.set(boardState(posFromFen(p.fen), p.side));
    note.textContent = uci === p.uci
      ? `${p.san} — это ход из партии, он и был ошибкой. Попробуйте другой.`
      : 'Это не лучший ход. Попробуйте ещё или нажмите «Показать ответ».';
  }

  function showAnswer(): void {
    if (!training) return;
    const i = training.list[training.at];
    const p = plies[i];
    const top = lines[i][0];
    training.solved = true;
    cg.set(boardState(posFromFen(p.fen), null));
    cg.setAutoShapes([arrow(top.pv[0], 'green')]);
    $('review-note').textContent = `Ответ: ${sanOf(p.fen, top.pv[0])}. Продолжение: ${sanLine(p.fen, top.pv)}.`;
  }

  function stopTraining(): void {
    const at = training?.list[training.at] ?? current;
    training = null;
    $('train-start').classList.remove('hidden');
    $('train-controls').classList.add('hidden');
    select(at);
  }

  $('review-run').onclick = () => void analyse(pgnBox.value);
  $<HTMLInputElement>('review-file').onchange = async (ev) => {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (file) pgnBox.value = await file.text();
  };
  $('review-prev').onclick = () => select(current - 1);
  $('review-next').onclick = () => select(current + 1);
  $('review-flip').onclick = () => {
    orientation = orientation === 'white' ? 'black' : 'white';
    if (training) showTask();
    else select(current);
  };
  $('review-other').onclick = () => {
    if (training) stopTraining();
    stage('input');
  };
  $('train-white').onclick = () => startTraining('white');
  $('train-black').onclick = () => startTraining('black');
  $('train-show').onclick = showAnswer;
  $('train-stop').onclick = stopTraining;
  $('train-next').onclick = () => {
    if (!training) return;
    if (training.at + 1 >= training.list.length) {
      stopTraining();
      $('review-note').textContent = 'Все задачи пройдены.';
      return;
    }
    training.at++;
    showTask();
  };
  window.addEventListener('keydown', (ev) => {
    if ($('view-review').classList.contains('hidden') || ev.target === pgnBox) return;
    if (ev.key === 'ArrowLeft') select(current - 1);
    if (ev.key === 'ArrowRight') select(current + 1);
  });

  return {
    load(pgn: string): void {
      pgnBox.value = pgn;
      void analyse(pgn);
    },
  };
}
