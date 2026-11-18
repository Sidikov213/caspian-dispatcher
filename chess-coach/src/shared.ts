// Общие шахматные помощники: позиция, запись ходов, оценки.
import { Chess } from 'chessops/chess';
import { chessgroundDests } from 'chessops/compat';
import { makeFen, parseFen } from 'chessops/fen';
import { makeSan } from 'chessops/san';
import type { Move, NormalMove } from 'chessops/types';
import { makeUci, parseSquare, parseUci } from 'chessops/util';
import type { Config } from 'chessground/config';
import type { Key } from 'chessground/types';
import type { Line } from './engine';

export type Side = 'white' | 'black';

export const posFromFen = (fen: string): Chess => Chess.fromSetup(parseFen(fen).unwrap()).unwrap();
export const fenOf = (pos: Chess): string => makeFen(pos.toSetup());

/** Запись хода как у движка: рокировка — король на две клетки (e1g1), а не «король бьёт ладью». */
export function uciOf(pos: Chess, move: Move): string {
  if ('from' in move) {
    const piece = pos.board.get(move.from);
    const target = pos.board.get(move.to);
    if (piece?.role === 'king' && target?.role === 'rook' && target.color === piece.color) {
      const file = move.to > move.from ? 6 : 2;
      return makeUci({ from: move.from, to: (move.from >> 3) * 8 + file });
    }
  }
  return makeUci(move);
}

/** Ход пользователя с доски; пешка на последней горизонтали превращается в ферзя. */
export function userMove(pos: Chess, orig: string, dest: string): NormalMove | undefined {
  const from = parseSquare(orig);
  const to = parseSquare(dest);
  if (from === undefined || to === undefined) return undefined;
  const move: NormalMove = { from, to };
  const rank = to >> 3;
  if (pos.board.get(from)?.role === 'pawn' && (rank === 0 || rank === 7)) move.promotion = 'queen';
  return pos.isLegal(move) ? move : undefined;
}

/** Линия движка в обычной записи: «12. Nf3 Nc6 13. Bb5». */
export function sanLine(fen: string, ucis: string[], max = 6): string {
  const pos = posFromFen(fen);
  const out: string[] = [];
  for (const uci of ucis.slice(0, max)) {
    const move = parseUci(uci);
    if (!move || !pos.isLegal(move)) break;
    if (pos.turn === 'white') out.push(`${pos.fullmoves}.`);
    else if (out.length === 0) out.push(`${pos.fullmoves}…`);
    out.push(makeSan(pos, move));
    pos.play(move);
  }
  return out.join(' ');
}

export function sanOf(fen: string, uci: string): string {
  const pos = posFromFen(fen);
  const move = parseUci(uci);
  return move && pos.isLegal(move) ? makeSan(pos, move) : uci;
}

/** Шансы белых на победу в процентах (формула Lichess). */
export const winPct = (cp: number): number => 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);

export const winPctFor = (cp: number, side: Side): number => (side === 'white' ? winPct(cp) : 100 - winPct(cp));

export function fmtEval(line: Pick<Line, 'cp' | 'mate'>): string {
  if (Math.abs(line.cp) >= 10000) return line.cp > 0 ? 'мат, 1–0' : 'мат, 0–1';
  if (line.mate !== undefined) return `${line.mate > 0 ? '' : '−'}М${Math.abs(line.mate)}`;
  const v = line.cp / 100;
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}`;
}

export type Grade = 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder';

export const GRADE_LABEL: Record<Grade, string> = {
  best: 'Лучший ход',
  good: 'Хороший ход',
  inaccuracy: 'Неточность',
  mistake: 'Ошибка',
  blunder: 'Зевок',
};

export const GRADE_MARK: Record<Grade, string> = { best: '', good: '', inaccuracy: '?!', mistake: '?', blunder: '??' };

/** Оценка хода по потере шансов на победу, в процентных пунктах. */
export function grade(loss: number, isBest: boolean): Grade {
  if (isBest) return 'best';
  if (loss >= 20) return 'blunder';
  if (loss >= 10) return 'mistake';
  if (loss >= 5) return 'inaccuracy';
  return 'good';
}

/** Оценка конечной позиции без движка; null — партия не окончена. */
export function terminalLine(pos: Chess): Line | null {
  if (!pos.isEnd()) return null;
  const winner = pos.outcome()?.winner;
  if (!winner) return { multipv: 1, depth: 0, cp: 0, pv: [] };
  const sign = winner === 'white' ? 1 : -1;
  return { multipv: 1, depth: 0, cp: sign * 10000, pv: [] };
}

/** Состояние доски chessground для позиции. movable — чьими фигурами можно ходить. */
export function boardState(pos: Chess, movable: Side | 'both' | null, lastUci?: string): Config {
  return {
    fen: fenOf(pos),
    turnColor: pos.turn,
    check: pos.isCheck(),
    lastMove: lastUci ? [lastUci.slice(0, 2) as Key, lastUci.slice(2, 4) as Key] : undefined,
    movable: {
      free: false,
      color: movable ?? undefined,
      dests: movable ? (chessgroundDests(pos) as Map<Key, Key[]>) : new Map(),
      showDests: true,
    },
  };
}

export function resultText(pos: Chess): string | null {
  if (!pos.isEnd()) return null;
  if (pos.isCheckmate()) return pos.turn === 'white' ? 'Мат. Победили чёрные' : 'Мат. Победили белые';
  if (pos.isStalemate()) return 'Пат. Ничья';
  return 'Ничья';
}

export const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
