const { getYouTubeStats } = require('./stats');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

async function sync() {
    const statsData = await getYouTubeStats();
    if (statsData) {
        const dataPath = path.join(__dirname, 'dashboard', 'data.json');
        if (!fs.existsSync(path.dirname(dataPath))) {
            fs.mkdirSync(path.dirname(dataPath), { recursive: true });
        }
        fs.writeFileSync(dataPath, JSON.stringify(statsData, null, 2));
        console.log(`✅ Dashboard data updated at ${dataPath}`);
        
        try {
            console.log('🔄 Syncing dashboard with GitHub...');
            execSync('git add dashboard/data.json && git commit -m "Manual stats update" && git push origin master', { stdio: 'inherit' });
            console.log('✅ Live dashboard updated on Cloudflare Pages!');
        } catch (err) {
            console.warn('⚠️ GitHub sync failed or no changes.');
        }
    }
}

sync();
