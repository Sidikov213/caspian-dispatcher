// Обёртка над Stockfish (UCI) в Web Worker. Запросы идут по очереди; cancel() отменяет всё начатое.

export interface Line {
  multipv: number;
  depth: number;
  /** Оценка в сантипешках с точки зрения белых; мат переведён в большое число. */
  cp: number;
  /** Мат в N ходов с точки зрения белых (знак — кто матует). */
  mate?: number;
  pv: string[];
}

export interface Result {
  bestmove: string;
  lines: Line[];
}

export interface Options {
  depth?: number;
  movetime?: number;
  multipv?: number;
  /** Сила игры 0–20; 20 — полная. */
  skill?: number;
}

const MATE_CP = 10000;

export class Engine {
  private worker: Worker;
  private ready: Promise<void>;
  private queue: Promise<unknown> = Promise.resolve();
  private onLine: ((line: string) => void) | null = null;
  private generation = 0;

  constructor() {
    this.worker = new Worker(new URL('engine/stockfish-19-lite-single.js', document.baseURI));
    this.worker.onmessage = (ev) => {
      if (typeof ev.data === 'string') this.onLine?.(ev.data);
    };
    this.ready = this.command('uci', 'uciok').then(() => this.command('isready', 'readyok'));
  }

  private command(cmd: string, waitFor: string): Promise<void> {
    return new Promise((resolve) => {
      this.onLine = (line) => {
        if (line.startsWith(waitFor)) {
          this.onLine = null;
          resolve();
        }
      };
      this.worker.postMessage(cmd);
    });
  }

  /** Отменяет текущий и все ожидающие расчёты: их промисы вернут null. */
  cancel(): void {
    this.generation++;
    this.worker.postMessage('stop');
  }

  analyse(fen: string, opts: Options, onUpdate?: (lines: Line[]) => void): Promise<Result | null> {
    const gen = this.generation;
    const run = async (): Promise<Result | null> => {
      await this.ready;
      if (gen !== this.generation) return null;
      const whiteToMove = fen.split(' ')[1] !== 'b';
      const lines = new Map<number, Line>();
      const sorted = () => [...lines.values()].sort((a, b) => a.multipv - b.multipv);
      this.worker.postMessage(`setoption name MultiPV value ${opts.multipv ?? 1}`);
      this.worker.postMessage(`setoption name Skill Level value ${opts.skill ?? 20}`);
      this.worker.postMessage(`position fen ${fen}`);
      const bestmove = await new Promise<string>((resolve) => {
        this.onLine = (line) => {
          if (line.startsWith('info ')) {
            const parsed = parseInfo(line, whiteToMove);
            if (parsed) {
              lines.set(parsed.multipv, parsed);
              onUpdate?.(sorted());
            }
          } else if (line.startsWith('bestmove')) {
            this.onLine = null;
            resolve(line.split(' ')[1] ?? '');
          }
        };
        this.worker.postMessage(opts.movetime ? `go movetime ${opts.movetime}` : `go depth ${opts.depth ?? 12}`);
      });
      if (gen !== this.generation) return null;
      return { bestmove, lines: sorted() };
    };
    const next = this.queue.then(run, run);
    this.queue = next;
    return next;
  }
}

function parseInfo(line: string, whiteToMove: boolean): Line | null {
  if (line.includes('upperbound') || line.includes('lowerbound')) return null;
  const t = line.split(' ');
  const pvAt = t.indexOf('pv');
  const scoreAt = t.indexOf('score');
  if (pvAt < 0 || scoreAt < 0) return null;
  const num = (key: string) => {
    const i = t.indexOf(key);
    return i < 0 ? undefined : Number(t[i + 1]);
  };
  const sign = whiteToMove ? 1 : -1;
  const value = Number(t[scoreAt + 2]);
  let cp: number;
  let mate: number | undefined;
  if (t[scoreAt + 1] === 'mate') {
    mate = sign * value;
    cp = Math.sign(mate) * (MATE_CP - Math.abs(mate) * 10);
  } else {
    cp = sign * value;
  }
  return { multipv: num('multipv') ?? 1, depth: num('depth') ?? 0, cp, mate, pv: t.slice(pvAt + 1) };
}
