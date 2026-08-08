#!/bin/bash
# 遍历所有文件，跳过大于200MB的文件
find . -type f -size +200M -printf "%P\n" > bigfiles.txt
# 正常添加全部文件
git add .
# 把大文件从暂存区剔除
while read file; do
  git reset HEAD -- "$file"
done < bigfiles.txt
# 删除临时记录文件
rm -f bigfiles.txt
echo "已完成添加，自动过滤200MB以上大文件"
