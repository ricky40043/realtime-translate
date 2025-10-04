#!/bin/bash

echo "🚀 上傳即時翻譯字幕系統到 GitHub"
echo "=================================="

# 檢查是否有未提交的變更
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  發現未提交的變更，正在提交..."
    git add .
    git commit -m "最終更新：準備上傳到 GitHub"
fi

echo ""
echo "📋 請先在 GitHub 建立新倉庫："
echo "1. 前往 https://github.com/new"
echo "2. Repository name: realtime-translate"
echo "3. Description: 即時翻譯字幕系統 - 支援多人協作、語音辨識、即時翻譯"
echo "4. 選擇 Public"
echo "5. 不要初始化任何檔案"
echo "6. 點擊 'Create repository'"
echo ""

read -p "已建立 GitHub 倉庫了嗎？請輸入你的 GitHub 用戶名: " github_username

if [ -z "$github_username" ]; then
    echo "❌ 請提供 GitHub 用戶名"
    exit 1
fi

echo ""
echo "🔗 設定遠端倉庫連結..."
git remote add origin "https://github.com/$github_username/realtime-translate.git" 2>/dev/null || {
    echo "⚠️  遠端倉庫已存在，更新 URL..."
    git remote set-url origin "https://github.com/$github_username/realtime-translate.git"
}

echo ""
echo "🌟 重命名主分支為 main..."
git branch -M main

echo ""
echo "📤 上傳到 GitHub..."
echo "Repository URL: https://github.com/$github_username/realtime-translate"

if git push -u origin main; then
    echo ""
    echo "🎉 上傳成功！"
    echo "=================================="
    echo ""
    echo "📊 專案統計："
    echo "• 檔案數量: $(git ls-files | wc -l | tr -d ' ') 個"
    echo "• 提交記錄: $(git rev-list --count HEAD) 個"
    echo "• 分支: main"
    echo ""
    echo "🌐 GitHub 連結："
    echo "• 倉庫: https://github.com/$github_username/realtime-translate"
    echo "• 設定: https://github.com/$github_username/realtime-translate/settings"
    echo ""
    echo "📋 建議後續步驟："
    echo "1. 在 GitHub 上添加 topics: translation, real-time, websocket, vue3, fastapi"
    echo "2. 檢查 README.md 顯示是否正常"
    echo "3. 考慮建立第一個 Release (v1.0.0)"
    echo "4. 邀請朋友測試和 star ⭐"
    echo ""
    echo "🎊 你的即時翻譯系統已成功上傳到 GitHub！"
else
    echo ""
    echo "❌ 上傳失敗！"
    echo "=================================="
    echo ""
    echo "🔍 可能的原因："
    echo "1. GitHub 倉庫尚未建立"
    echo "2. 用戶名錯誤"
    echo "3. 沒有推送權限"
    echo "4. 網路連線問題"
    echo ""
    echo "💡 解決方案："
    echo "1. 確認 GitHub 倉庫已建立：https://github.com/$github_username/realtime-translate"
    echo "2. 檢查 GitHub 登入狀態"
    echo "3. 嘗試手動執行："
    echo "   git remote add origin https://github.com/$github_username/realtime-translate.git"
    echo "   git push -u origin main"
fi