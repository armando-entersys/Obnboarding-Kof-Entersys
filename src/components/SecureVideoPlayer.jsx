/**
 * SecureVideoPlayer.jsx
 * Componente de video con sistema anti-skip (Heartbeat) según MD050.
 *
 * Características:
 * - Bloqueo de adelanto (seek-bar lock)
 * - Envío de heartbeats cada 5 segundos
 * - Persistencia de progreso en el servidor
 * - Fallback a almacenamiento local si el servidor no responde
 */

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { config } from '../config/environment';

const API_BASE_URL = config.urls.api;
const HEARTBEAT_INTERVAL = 15000; // 15 segundos - optimizado para reducir carga del servidor 3x

const SecureVideoPlayer = ({
  videoSrc,
  videoId = 'seguridad-2024',
  userId,
  onComplete,
  posterImage = null,
  title = 'Video de Capacitación',
  examPath = '/formulario-curso-seguridad'
}) => {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const lastTimeRef = useRef(0);
  const maxWatchedTimeRef = useRef(0);
  const previousTimeRef = useRef(0); // Para detectar seeks
  const isSeekingRef = useRef(false); // Flag para bloquear actualizaciones durante seek

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [progress, setProgress] = useState(0);
  const [totalWatched, setTotalWatched] = useState(0);
  const [displayWatched, setDisplayWatched] = useState(0); // Tiempo mostrado en UI (sincronizado con video)
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [canAccessExam, setCanAccessExam] = useState(false);

  // Cargar progreso guardado al iniciar
  useEffect(() => {
    const loadProgress = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/progress/${userId}/${videoId}`,
          { method: 'GET' }
        );

        if (response.ok) {
          const data = await response.json();
          setTotalWatched(data.seconds_accumulated);
          maxWatchedTimeRef.current = data.seconds_accumulated;
        }
      } catch (err) {
        // Si falla, intentar cargar de localStorage
        const localProgress = localStorage.getItem(`video_progress_${userId}_${videoId}`);
        if (localProgress) {
          const parsed = JSON.parse(localProgress);
          setTotalWatched(parsed.seconds);
          maxWatchedTimeRef.current = parsed.seconds;
        }
      }
      setIsLoading(false);
    };

    if (userId) {
      loadProgress();
    } else {
      setIsLoading(false);
    }
  }, [userId, videoId]);

  // Enviar heartbeat al servidor
  const sendHeartbeat = useCallback(async (secondsWatched) => {
    if (!userId || secondsWatched <= 0) return;

    console.log(`[Heartbeat] Enviando ${secondsWatched.toFixed(2)}s para user ${userId}`);

    try {
      const response = await fetch(`${API_BASE_URL}/video-heartbeat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          video_id: videoId,
          seconds_watched: secondsWatched
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log(`[Heartbeat] Respuesta OK: total_seconds=${data.total_seconds}`);
        setTotalWatched(data.total_seconds);
        maxWatchedTimeRef.current = Math.max(maxWatchedTimeRef.current, data.total_seconds);
      } else {
        console.error(`[Heartbeat] Error HTTP: ${response.status}`);
      }
    } catch (err) {
      console.error('[Heartbeat] Error de red:', err);
      // Fallback: guardar en localStorage
      setTotalWatched(prev => {
        const newTotal = prev + secondsWatched;
        const currentProgress = {
          seconds: newTotal,
          timestamp: Date.now()
        };
        localStorage.setItem(
          `video_progress_${userId}_${videoId}`,
          JSON.stringify(currentProgress)
        );
        return newTotal;
      });
    }
  }, [userId, videoId]);

  // Iniciar intervalo de heartbeat cuando el video está reproduciéndose
  useEffect(() => {
    if (isPlaying && userId) {
      heartbeatIntervalRef.current = setInterval(() => {
        const video = videoRef.current;
        if (video && !video.paused) {
          const timeDiff = video.currentTime - lastTimeRef.current;
          if (timeDiff > 0 && timeDiff <= 6) { // Solo enviar si el avance es razonable
            sendHeartbeat(timeDiff);
          }
          lastTimeRef.current = video.currentTime;
        }
      }, HEARTBEAT_INTERVAL);
    }

    return () => {
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
      }
    };
  }, [isPlaying, userId, sendHeartbeat]);

  // Verificador constante anti-skip - se ejecuta cada 100ms para atrapar clics rápidos
  useEffect(() => {
    const antiSkipInterval = setInterval(() => {
      const video = videoRef.current;
      if (video && video.currentTime > maxWatchedTimeRef.current + 0.5) {
        console.log(`[AntiSkip] Forzando regreso: ${video.currentTime.toFixed(1)}s -> ${maxWatchedTimeRef.current.toFixed(1)}s`);
        video.currentTime = maxWatchedTimeRef.current;
      }
    }, 100); // Verificar cada 100ms

    return () => clearInterval(antiSkipInterval);
  }, []);

  // Manejar evento de metadata cargada
  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (video) {
      setDuration(video.duration);
      setIsLoading(false);
      // Forzar velocidad normal
      video.playbackRate = 1.0;
    }
  };

  // Bloquear teclas de adelanto (flechas, etc.)
  const handleKeyDown = (e) => {
    const video = videoRef.current;
    if (!video) return;

    // Bloquear flechas derecha y L (adelantar)
    if (e.key === 'ArrowRight' || e.key === 'l' || e.key === 'L') {
      const newTime = video.currentTime + (e.key === 'ArrowRight' ? 5 : 10);
      if (newTime > maxWatchedTimeRef.current + 0.5) {
        e.preventDefault();
        e.stopPropagation();
        console.log('[Video] Tecla de adelanto bloqueada');
      }
    }
  };

  // Añadir listener de teclado cuando el video está en foco
  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.addEventListener('keydown', handleKeyDown, true);
      return () => {
        video.removeEventListener('keydown', handleKeyDown, true);
      };
    }
  }, []);

  // Bloquear cambio de velocidad de reproducción
  const handleRateChange = () => {
    const video = videoRef.current;
    if (video && video.playbackRate !== 1.0) {
      console.log('[Video] Bloqueando cambio de velocidad');
      video.playbackRate = 1.0;
    }
  };

  // Manejar actualización del tiempo
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (video && !isSeekingRef.current) {
      const currentVideoTime = video.currentTime;

      // Detectar si hubo un salto grande (seek adelante no permitido)
      const timeDiff = currentVideoTime - previousTimeRef.current;
      if (timeDiff > 2 && currentVideoTime > maxWatchedTimeRef.current + 1) {
        // Salto no permitido, regresar al máximo visto
        console.log(`[Video] Bloqueando seek: de ${previousTimeRef.current.toFixed(1)}s a ${currentVideoTime.toFixed(1)}s (max: ${maxWatchedTimeRef.current.toFixed(1)}s)`);
        video.currentTime = maxWatchedTimeRef.current;
        return;
      }

      setCurrentTime(currentVideoTime);
      setProgress((currentVideoTime / video.duration) * 100);
      setDisplayWatched(currentVideoTime);

      // Actualizar el máximo visto solo si es un avance pequeño (reproducción normal)
      if (currentVideoTime > maxWatchedTimeRef.current && timeDiff <= 2) {
        maxWatchedTimeRef.current = currentVideoTime;
      }

      previousTimeRef.current = currentVideoTime;
    }
  };

  // Bloquear el seek más allá del tiempo máximo visto
  const handleSeeking = () => {
    isSeekingRef.current = true;
    const video = videoRef.current;
    if (video) {
      const maxAllowed = maxWatchedTimeRef.current;
      // Si intenta ir más adelante del máximo permitido, regresarlo inmediatamente
      if (video.currentTime > maxAllowed + 0.5) {
        console.log(`[Video] Seeking bloqueado: intentó ir a ${video.currentTime.toFixed(1)}s, max permitido: ${maxAllowed.toFixed(1)}s`);
        // Forzar regreso inmediato sin pausar para evitar evasión
        video.currentTime = maxAllowed;
      }
    }
  };

  // También bloquear en el evento seeked (después de que el seek se completa)
  const handleSeeked = () => {
    const video = videoRef.current;
    const maxAllowed = maxWatchedTimeRef.current;
    if (video && video.currentTime > maxAllowed + 0.5) {
      console.log(`[Video] Seeked bloqueado: forzando regreso a ${maxAllowed.toFixed(1)}s`);
      video.currentTime = maxAllowed;
    }
    // Pequeño delay antes de permitir actualizaciones de nuevo
    setTimeout(() => {
      isSeekingRef.current = false;
      if (video) {
        previousTimeRef.current = video.currentTime;
        // Verificación adicional después del delay
        if (video.currentTime > maxAllowed + 0.5) {
          video.currentTime = maxAllowed;
        }
      }
    }, 100);
  };

  // Manejar play
  const handlePlay = () => {
    setIsPlaying(true);
    lastTimeRef.current = videoRef.current?.currentTime || 0;
  };

  // Manejar pause
  const handlePause = () => {
    setIsPlaying(false);
    // Enviar heartbeat final al pausar
    const video = videoRef.current;
    if (video) {
      const timeDiff = video.currentTime - lastTimeRef.current;
      if (timeDiff > 0) {
        sendHeartbeat(timeDiff);
      }
    }
  };

  // Manejar fin del video
  const handleEnded = () => {
    setIsPlaying(false);
    const video = videoRef.current;
    if (video) {
      // Enviar último heartbeat
      const timeDiff = video.currentTime - lastTimeRef.current;
      if (timeDiff > 0) {
        sendHeartbeat(timeDiff);
      }
      // Actualizar display al 100%
      setDisplayWatched(video.duration);
      maxWatchedTimeRef.current = video.duration;
    }
    // Activar acceso al examen automáticamente cuando termina el video
    setCanAccessExam(true);
    if (onComplete) {
      onComplete({ authorized: true, progress_percentage: 100, exam_url: examPath });
    }
  };

  // Validar si el usuario puede acceder al examen (llamado manualmente por botón)
  const validateCompletion = async () => {
    if (!duration) return;

    const video = videoRef.current;
    const currentWatched = video ? video.currentTime : displayWatched;
    const watchedPercentage = (currentWatched / duration) * 100;

    console.log(`[Validate] Progreso: ${watchedPercentage.toFixed(1)}%`);

    if (watchedPercentage >= 90) {
      setCanAccessExam(true);
      if (onComplete) {
        onComplete({ authorized: true, progress_percentage: watchedPercentage, exam_url: examPath });
      }
      return;
    }

    // Si tiene userId, intentar validar con el servidor
    if (userId) {
      try {
        const response = await fetch(`${API_BASE_URL}/validate-completion`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id: userId,
            video_id: videoId,
            video_duration: duration
          })
        });

        if (response.ok) {
          const data = await response.json();
          setCanAccessExam(data.authorized);

          if (data.authorized && onComplete) {
            onComplete(data);
          }
        }
      } catch (err) {
        // Si falla el servidor, usar validación local
        console.warn('Error validando con servidor, usando validación local:', err);
        if (watchedPercentage >= 90) {
          setCanAccessExam(true);
        }
      }
    }
  };

  // Navegar al formulario de examen
  const handleGoToExam = () => {
    navigate(examPath);
  };

  // Formatear tiempo en mm:ss
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Prevenir clic derecho
  const handleContextMenu = (e) => {
    e.preventDefault();
  };

  // Prevenir doble clic que permite adelantar el video
  const handleDoubleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('[Video] Doble clic bloqueado');
  };

  // Bloquear clics en la barra de progreso que intenten adelantar
  const handleVideoClick = (e) => {
    const video = videoRef.current;
    if (!video) return;

    // Obtener la posición del clic relativa al video
    const rect = video.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickPercent = clickX / rect.width;
    const clickTime = clickPercent * video.duration;

    // Si el clic intenta ir más allá del máximo permitido, bloquearlo
    if (clickTime > maxWatchedTimeRef.current + 1) {
      e.preventDefault();
      e.stopPropagation();
      console.log(`[Video] Clic en barra bloqueado: intentó ir a ${clickTime.toFixed(1)}s, max: ${maxWatchedTimeRef.current.toFixed(1)}s`);
      // Forzar el tiempo al máximo permitido
      video.currentTime = maxWatchedTimeRef.current;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 bg-gray-900 rounded-lg">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500"></div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
        {userId && (
          <p className="text-sm text-gray-500">
            Tiempo acumulado: {formatTime(displayWatched)}
            {duration > 0 && ` / ${formatTime(duration)} (${Math.round((displayWatched / duration) * 100)}%)`}
          </p>
        )}
      </div>

      {/* Video Container */}
      <div
        className="relative bg-black rounded-lg overflow-hidden shadow-lg group"
        onContextMenu={handleContextMenu}
      >
        <video
          ref={videoRef}
          className="w-full aspect-video cursor-pointer"
          src={videoSrc}
          poster={posterImage}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onSeeking={handleSeeking}
          onSeeked={handleSeeked}
          onPlay={handlePlay}
          onPause={handlePause}
          onEnded={handleEnded}
          onRateChange={handleRateChange}
          onClick={() => {
            const video = videoRef.current;
            if (video) {
              if (video.paused) {
                video.play().catch(() => {});
              } else {
                video.pause();
              }
            }
          }}
          controlsList="nodownload noplaybackrate"
          disablePictureInPicture
          playsInline
        >
          Tu navegador no soporta el elemento de video.
        </video>

        {/* Controles personalizados - sin barra de avance */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4 opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="flex items-center justify-between">
            {/* Play/Pause */}
            <button
              onClick={() => {
                const video = videoRef.current;
                if (video) {
                  if (video.paused) {
                    video.play().catch(() => {});
                  } else {
                    video.pause();
                  }
                }
              }}
              className="text-white hover:text-green-400 transition-colors"
              aria-label={isPlaying ? 'Pausar' : 'Reproducir'}
            >
              {isPlaying ? (
                <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                </svg>
              ) : (
                <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z"/>
                </svg>
              )}
            </button>

            {/* Tiempo */}
            <div className="text-white text-sm font-mono">
              {formatTime(currentTime)} / {formatTime(duration)}
            </div>

            {/* Volumen */}
            <button
              onClick={() => {
                const video = videoRef.current;
                if (video) {
                  video.muted = !video.muted;
                }
              }}
              className="text-white hover:text-green-400 transition-colors"
              aria-label="Volumen"
            >
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
              </svg>
            </button>

            {/* Pantalla completa */}
            <button
              onClick={() => {
                const video = videoRef.current;
                if (video) {
                  if (document.fullscreenElement) {
                    document.exitFullscreen();
                  } else {
                    video.requestFullscreen().catch(() => {});
                  }
                }
              }}
              className="text-white hover:text-green-400 transition-colors"
              aria-label="Pantalla completa"
            >
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Icono de play grande en el centro cuando está pausado */}
        {!isPlaying && (
          <div
            className="absolute inset-0 flex items-center justify-center cursor-pointer"
            onClick={() => {
              const video = videoRef.current;
              if (video) video.play().catch(() => {});
            }}
          >
            <div className="bg-black/50 rounded-full p-4">
              <svg className="w-16 h-16 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
        )}

        {/* Barra de progreso visual (solo lectura, no clickeable) */}
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700 pointer-events-none">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${(currentTime / (duration || 1)) * 100}%` }}
          />
        </div>
      </div>

      {/* Progress Info */}
      <div className="mt-4 p-4 bg-gray-50 rounded-lg">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-gray-700">Progreso de visualización</span>
          <span className="text-sm text-gray-500">
            {Math.round((displayWatched / (duration || 1)) * 100)}% completado
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-green-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${Math.min((displayWatched / (duration || 1)) * 100, 100)}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-gray-500">
          Debe visualizar al menos el 90% del video para acceder al examen.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

    </div>
  );
};

export default SecureVideoPlayer;
