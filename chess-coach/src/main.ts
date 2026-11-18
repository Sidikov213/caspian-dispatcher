import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './style.css';
import { Engine } from './engine';
import { initPlay } from './play';
import { initReview } from './review';
import { $ } from './shared';

const engine = new Engine();
engine
  .analyse('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', { depth: 1 })
  .then(() => ($('engine-status').textContent = 'Stockfish 19 готов'));

function show(tab: 'play' | 'review'): void {
  for (const t of ['play', 'review'] as const) {
    $(`view-${t}`).classList.toggle('hidden', t !== tab);
    $(`tab-${t}`).classList.toggle('active', t === tab);
  }
  window.dispatchEvent(new Event('resize'));
}

const review = initReview(engine);
initPlay(engine, (pgn) => {
  show('review');
  review.load(pgn);
});

$('tab-play').onclick = () => show('play');
$('tab-review').onclick = () => show('review');
