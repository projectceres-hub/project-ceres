param(
    [string]$Message = "chore: update Ceres"
)

git status
git add -A
git commit -m $Message
git push