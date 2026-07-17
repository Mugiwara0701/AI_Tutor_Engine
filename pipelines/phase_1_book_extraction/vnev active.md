. .venv/Scripts/activate

python -m pytest tests/ -v

.venv/Scripts/python.exe pipeline.py --force

pip uninstall torch torchvision torchaudio
pip install torch --index-url https://download.pytorch.org/whl/cu124

.venv/Scripts/python.exe -m pytest tests/test_m5_3_e2e_verification.py -v
