@echo off
title TEFL App

set PATH=%PATH%;C:\Users\areli\AppData\Local\Programs\Ollama
set PATH=%PATH%;C:\ffmpeg\bin

:: Start Ollama CPU-only (scoped to its own cmd window only)
echo Starting Ollama...
start "Ollama" cmd /k "set CUDA_VISIBLE_DEVICES=-1 && ollama serve"

echo Waiting for Ollama to start...
timeout /t 8 /nobreak >nul

:: Flask starts WITHOUT CUDA_VISIBLE_DEVICES set, so PyTorch can see the GPU
echo Starting TEFL App...
call venv\Scripts\activate
python app.py