# 我的记账本

## 启动

```bash
cd account_book
pip install -r requirements.txt
streamlit run app.py
```

数据默认保存在 `account_book/data/account_book.db`。金额以“分”存储，避免浮点误差。
