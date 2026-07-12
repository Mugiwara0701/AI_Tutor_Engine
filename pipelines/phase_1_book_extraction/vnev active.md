. .venv/Scripts/activate

python -m pytest tests/ -v

pip uninstall torch torchvision torchaudio
pip install torch --index-url https://download.pytorch.org/whl/cu124
