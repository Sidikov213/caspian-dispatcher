"""ИИ-диспетчер: конвейер из раздела 3 CLAUDE.md (affected → predict → do_nothing → alternatives →
лучший → Alert → accept под asyncio.Lock). Числа считает код, LLM пишет только текст.

TODO: весь конвейер. Эталонные числа — data/mock/*.json (их строит scripts/gen_mocks.py).
"""
