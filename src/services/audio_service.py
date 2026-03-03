import os
import subprocess
import logging
from typing import Optional

# Lazy import: whisper (e torch) são carregados apenas quando necessário
whisper = None

def _import_whisper():
    global whisper
    if whisper is None:
        try:
            import whisper as _whisper
            whisper = _whisper
        except ImportError:
            raise ImportError("openai-whisper não está instalado. Instale com: pip install openai-whisper")

# Configuração de log
logger = logging.getLogger(__name__)

class AudioService:
    """
    Serviço para transcrição de áudio utilizando o modelo Whisper da OpenAI.
    Requer FFmpeg instalado no sistema.
    """
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None

    def _load_model(self):
        """Carrega o modelo Whisper sob demanda."""
        if not self.model:
            logger.info(f"Carregando modelo Whisper: {self.model_size}")
            try:
                _import_whisper()
                self.model = whisper.load_model(self.model_size)
            except Exception as e:
                logger.error(f"Erro ao carregar modelo Whisper: {e}")
                raise

    def _configure_ffmpeg_path(self):
        """Adiciona caminhos conhecidos do FFmpeg ao PATH se não encontrado."""
        if self.is_ffmpeg_available():
            return

        known_paths = [
            r"C:\Users\Particular\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-essentials_build\bin",
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
        ]

        for path in known_paths:
            if os.path.exists(os.path.join(path, "ffmpeg.exe")):
                logger.info(f"FFmpeg encontrado em: {path}. Adicionando ao PATH.")
                os.environ["PATH"] += os.pathsep + path
                break

    def is_ffmpeg_available(self) -> bool:
        """Verifica se o FFmpeg está instalado e acessível no PATH."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def transcribe(self, audio_path: str) -> str:
        """
        Transcreve um arquivo de áudio para texto.
        
        Args:
            audio_path (str): Caminho absoluto do arquivo de áudio.
            
        Returns:
            str: Texto transcrito.
            
        Raises:
            RuntimeError: Se o FFmpeg não estiver instalado.
            FileNotFoundError: Se o arquivo de áudio não existir.
        """
        self._configure_ffmpeg_path()
        
        if not self.is_ffmpeg_available():
            # Tentar verificar novamente após adicionar ao PATH
            pass 

        if not self.is_ffmpeg_available():
            logger.error("FFmpeg não encontrado mesmo após verificar caminhos conhecidos.")
            raise RuntimeError("FFmpeg não está disponível. Por favor, instale o FFmpeg para utilizar a transcrição de áudio.")
        
        if not os.path.exists(audio_path):
            logger.error(f"Arquivo de áudio não encontrado: {audio_path}")
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

        try:
            self._load_model()
            logger.info(f"Iniciando transcrição do arquivo: {audio_path}")
            result = self.model.transcribe(audio_path)
            transcription = result["text"]
            logger.info("Transcrição concluída com sucesso.")
            return transcription
        except Exception as e:
            logger.error(f"Erro durante a transcrição: {e}")
            raise

# Singleton instance
audio_service = AudioService()
