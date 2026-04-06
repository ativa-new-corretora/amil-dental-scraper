import time
import random


def delay_humano(min_seg: float = 0.5, max_seg: float = 2.0, stop_flag=None) -> None:
    """Delay aleatório para simular comportamento humano."""
    tempo = random.uniform(min_seg, max_seg)
    if stop_flag:
        stop_flag.wait(timeout=tempo)
    else:
        time.sleep(tempo)


def pausa_estrategica(stop_flag=None) -> None:
    """
    Pausa estratégica de 60 segundos quando há problemas de carregamento ou resultados.
    Chamada apenas quando:
    - A página da Amil não carrega na segunda tentativa
    - Não há resultados na segunda tentativa de consulta
    """
    print("♻️ Pausa estratégica: 60s para reiniciar sessão...")
    
    if stop_flag:
        # Esperar 60s, mas verificar flag a cada 0.5s ou usar wait com timeout
        if stop_flag.wait(timeout=60):
            print("🛑 Pausa interrompida pelo usuário")
            return
    else:
        time.sleep(60)
        
    print("✅ Pausa concluída, continuando...")