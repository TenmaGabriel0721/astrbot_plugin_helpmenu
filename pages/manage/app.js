const { createApp, ref, onMounted } = Vue;

const TEMPLATE = `
<div class="max-w-6xl mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6">
    <div class="flex justify-between items-center border-b pb-4 mb-6">
        <div>
            <h1 class="text-2xl font-bold text-gray-800">帮助菜单可视化管理器</h1>
            <p class="text-sm text-gray-500 mt-1">管理你的 /help 帮助图文菜单内容，支持为分类和具体指令上传 Logo；留空时自动匹配 emoji。</p>
        </div>
        <div class="space-x-3">
            <button @click="addCategory" class="px-4 py-2 bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 transition font-medium">+ 新建分类</button>
            <button @click="saveMenu" :disabled="saving || uploading" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50">
                <span v-text="saving ? '保存中...' : '保存修改'"></span>
            </button>
        </div>
    </div>

    <div v-if="message" :class="message.type === 'success' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'" class="p-4 rounded-lg border mb-6 flex justify-between items-center">
        <span v-text="message ? message.text : ''"></span>
        <button @click="message = null" class="text-lg font-bold">&times;</button>
    </div>

    <div v-if="categories.length === 0" class="text-center py-12 text-gray-400">暂无分类，请点击右上角“新建分类”开始创建吧！</div>

    <div v-else class="space-y-6">
        <div v-for="(cat, catIdx) in categories" :key="catIdx" class="border rounded-xl bg-gray-50 p-4 relative">
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div class="flex items-center space-x-3 flex-grow min-w-0">
                    <div class="w-16 h-16 rounded-xl bg-white border flex items-center justify-center overflow-hidden text-2xl text-gray-400 flex-none">
                        <img v-if="cat.icon" :src="previewIcon(cat.icon)" class="w-full h-full object-contain" alt="分类Logo" @error="resolveIcon(cat.icon)">
                        <span v-else>📂</span>
                    </div>
                    <input type="text" v-model="cat.name" class="text-lg font-bold bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 focus:bg-white px-1 py-0.5 rounded outline-none w-64 max-w-full" placeholder="分类名称">
                    <div class="flex items-center gap-2 text-xs">
                        <button @click="uploadIcon('category', catIdx)" :disabled="uploading" class="px-2.5 py-1.5 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition text-gray-700 disabled:opacity-50">上传分类Logo</button>
                        <button v-if="cat.icon" @click="cat.icon = ''" class="px-2.5 py-1.5 bg-gray-100 text-gray-600 rounded-md hover:bg-gray-200 transition">清空Logo</button>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <div class="flex items-center bg-white border border-gray-300 rounded-md overflow-hidden">
                        <button @click="moveCategory(catIdx, -1)" :disabled="catIdx === 0" title="上移分类" class="px-2 py-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition">↑</button>
                        <span class="w-px h-5 bg-gray-200"></span>
                        <button @click="moveCategory(catIdx, 1)" :disabled="catIdx === categories.length - 1" title="下移分类" class="px-2 py-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition">↓</button>
                    </div>
                    <button @click="addCommand(catIdx)" class="text-sm px-2.5 py-1.5 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition text-gray-700">+ 添加指令</button>
                    <button @click="deleteCategory(catIdx)" :class="pendingDeleteIdx === catIdx ? 'bg-red-600 text-white hover:bg-red-700' : 'bg-red-50 text-red-600 hover:bg-red-100'" class="text-sm px-2.5 py-1.5 rounded-md transition" v-text="pendingDeleteIdx === catIdx ? '再次点击确认' : '删除分类'"></button>
                </div>
            </div>

            <div class="bg-white border rounded-lg divide-y">
                <div v-if="cat.commands.length === 0" class="p-4 text-center text-sm text-gray-400">该分类下暂无指令，点击“添加指令”开始吧。</div>
                <div v-else v-for="(cmd, cmdIdx) in cat.commands" :key="cmdIdx" class="p-3 flex flex-wrap items-center gap-3 hover:bg-gray-50">
                    <div class="w-14 h-14 rounded-xl bg-gray-100 border flex items-center justify-center overflow-hidden text-xl text-gray-400 flex-none">
                        <img v-if="cmd.icon" :src="previewIcon(cmd.icon)" class="w-full h-full object-contain" alt="指令Logo" @error="resolveIcon(cmd.icon)">
                        <span v-else>✨</span>
                    </div>
                    <div class="w-56 max-w-full">
                        <div class="flex items-center bg-gray-100 rounded px-2">
                            <input type="text" v-model="cmd.prefix" class="bg-transparent py-1.5 w-8 outline-none font-mono text-sm text-gray-600 text-center" placeholder="~" title="前缀（留空=自动，输入空格=无前缀）">
                            <input type="text" v-model="cmd.name" class="bg-transparent py-1.5 w-full outline-none font-medium text-sm text-gray-800" placeholder="指令名">
                        </div>
                    </div>
                    <div class="flex-grow min-w-64">
                        <input type="text" v-model="cmd.desc" class="w-full border border-gray-200 rounded px-3 py-1.5 text-sm text-gray-600 focus:border-blue-500 focus:outline-none" placeholder="输入指令功能说明描述...">
                    </div>
                    <div class="flex items-center gap-2 flex-none">
                        <div class="flex items-center bg-white border border-gray-300 rounded-md overflow-hidden">
                            <button @click="moveCommand(catIdx, cmdIdx, -1)" :disabled="cmdIdx === 0" title="上移指令" class="px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition">↑</button>
                            <span class="w-px h-4 bg-gray-200"></span>
                            <button @click="moveCommand(catIdx, cmdIdx, 1)" :disabled="cmdIdx === cat.commands.length - 1" title="下移指令" class="px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition">↓</button>
                        </div>
                        <button @click="uploadIcon('command', catIdx, cmdIdx)" :disabled="uploading" class="text-xs px-2.5 py-1.5 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition text-gray-700 disabled:opacity-50">上传Logo</button>
                        <button v-if="cmd.icon" @click="cmd.icon = ''" class="text-xs px-2.5 py-1.5 bg-gray-100 text-gray-600 rounded-md hover:bg-gray-200 transition">清空</button>
                        <button @click="deleteCommand(catIdx, cmdIdx)" class="text-gray-400 hover:text-red-500 transition text-xl px-2">&times;</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
`;

createApp({
    template: TEMPLATE,
    setup() {
        const categories = ref([]);
        const saving = ref(false);
        const uploading = ref(false);
        const message = ref(null);
        const pendingDeleteIdx = ref(-1);
        let bridge = null;
        const iconPreviewCache = ref({});
        const resolvingIcons = new Set();

        const showMessage = (text, type = 'success') => {
            message.value = { text, type };
            setTimeout(() => { message.value = null; }, 5000);
        };

        const initBridge = async () => {
            try {
                bridge = window.AstrBotPluginPage;
                if (!bridge) throw new Error('未检测到 Bridge 通信对象');
                await bridge.ready();
                await fetchMenu();
            } catch (err) {
                showMessage('通信初始化失败: ' + err.message, 'error');
                console.error(err);
            }
        };

        const previewIcon = (icon) => {
            if (!icon) return '';
            if (iconPreviewCache.value[icon]) return iconPreviewCache.value[icon];
            if (icon.startsWith('data:') || icon.startsWith('http://') || icon.startsWith('https://')) return icon;
            resolveIcon(icon);
            return '';
        };

        const resolveIcon = async (icon) => {
            if (!bridge || !icon || iconPreviewCache.value[icon] || resolvingIcons.has(icon)) return;
            if (icon.startsWith('data:') || icon.startsWith('http://') || icon.startsWith('https://')) return;
            resolvingIcons.add(icon);
            try {
                const result = await bridge.apiPost('icon/resolve', { icon });
                if (result && (result.success === true || result.success === 'true') && result.url) {
                    iconPreviewCache.value = { ...iconPreviewCache.value, [icon]: result.url };
                }
            } catch (err) {
                console.warn('Logo 预览解析失败:', err);
            } finally {
                resolvingIcons.delete(icon);
            }
        };

        const resolveMenuIcons = async () => {
            const icons = [];
            for (const cat of categories.value) {
                if (cat.icon) icons.push(cat.icon);
                for (const cmd of cat.commands) {
                    if (cmd.icon) icons.push(cmd.icon);
                }
            }
            await Promise.all([...new Set(icons)].map(resolveIcon));
        };

        const chooseImage = () => new Promise((resolve) => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/png,image/jpeg,image/webp,image/gif';
            input.style.display = 'none';
            const cleanup = () => {
                input.onchange = null;
                input.remove();
            };
            input.onchange = () => {
                const file = input.files && input.files[0] ? input.files[0] : null;
                cleanup();
                resolve(file);
            };
            document.body.appendChild(input);
            input.click();
        });

        const readFileAsDataURL = (file) => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error || new Error('读取图片失败'));
            reader.readAsDataURL(file);
        });

        const uploadIcon = async (type, catIdx, cmdIdx = null) => {
            if (!bridge || uploading.value) return;
            const file = await chooseImage();
            if (!file) return;
            if (file.size > 5 * 1024 * 1024) {
                showMessage('图片不能超过 5MB', 'error');
                return;
            }
            uploading.value = true;
            try {
                const data = await readFileAsDataURL(file);
                const result = await bridge.apiPost('icon', { filename: file.name, data });
                if (!result || !(result.success === true || result.success === 'true') || !result.path) {
                    throw new Error((result && (result.message || result.error)) || '上传响应错误');
                }
                if (type === 'category') {
                    categories.value[catIdx].icon = result.path;
                } else {
                    categories.value[catIdx].commands[cmdIdx].icon = result.path;
                }
                await resolveIcon(result.path);
                showMessage('Logo 上传成功，记得保存修改。');
            } catch (err) {
                showMessage('上传失败: ' + err.message, 'error');
            } finally {
                uploading.value = false;
            }
        };

        const fetchMenu = async () => {
            try {
                if (!bridge) return;
                const data = await bridge.apiGet('menu');
                const list = [];
                const menuSource = data.success !== undefined && data.data !== undefined ? data.data : data;
                for (const [catName, cmdMap] of Object.entries(menuSource || {})) {
                    const commands = [];
                    const catIcon = cmdMap && typeof cmdMap === 'object' ? (cmdMap.__icon__ || '') : '';
                    for (const [cmdName, cmdInfo] of Object.entries(cmdMap || {})) {
                        if (cmdName === '__icon__') continue;
                        let desc = '';
                        let icon = '';
                        let prefix = undefined;  // undefined 表示使用默认逻辑
                        if (cmdInfo && typeof cmdInfo === 'object') {
                            desc = cmdInfo.desc || '';
                            icon = cmdInfo.icon || '';
                            prefix = cmdInfo.prefix !== undefined ? cmdInfo.prefix : undefined;
                        } else {
                            desc = String(cmdInfo || '');
                        }
                        commands.push({ name: cmdName, desc, icon, prefix });
                    }
                    list.push({ name: catName, icon: catIcon, commands });
                }
                categories.value = list;
                resolveMenuIcons();
            } catch (err) {
                showMessage('加载数据失败: ' + err.message, 'error');
            }
        };

        const addCategory = () => {
            categories.value.push({ name: '新分类_' + (categories.value.length + 1), icon: '', commands: [] });
        };

        const deleteCategory = (idx) => {
            const cat = categories.value[idx];
            if (!cat) return;
            if (pendingDeleteIdx.value === idx) {
                categories.value.splice(idx, 1);
                pendingDeleteIdx.value = -1;
                return;
            }
            pendingDeleteIdx.value = idx;
            showMessage(`再次点击「删除分类」以确认删除 "${cat.name}"`, 'error');
            setTimeout(() => {
                if (pendingDeleteIdx.value === idx) pendingDeleteIdx.value = -1;
            }, 5000);
        };

        const addCommand = (catIdx) => {
            categories.value[catIdx].commands.push({ name: '', desc: '', icon: '', prefix: undefined });
        };

        const deleteCommand = (catIdx, cmdIdx) => {
            categories.value[catIdx].commands.splice(cmdIdx, 1);
        };

        const moveCategory = (idx, delta) => {
            const target = idx + delta;
            const list = categories.value;
            if (target < 0 || target >= list.length) return;
            const [item] = list.splice(idx, 1);
            list.splice(target, 0, item);
            if (pendingDeleteIdx.value !== -1) pendingDeleteIdx.value = -1;
        };

        const moveCommand = (catIdx, cmdIdx, delta) => {
            const cmds = categories.value[catIdx] && categories.value[catIdx].commands;
            if (!cmds) return;
            const target = cmdIdx + delta;
            if (target < 0 || target >= cmds.length) return;
            const [item] = cmds.splice(cmdIdx, 1);
            cmds.splice(target, 0, item);
        };

        const saveMenu = async () => {
            if (!bridge) return;
            saving.value = true;
            try {
                const payload = {};
                for (const cat of categories.value) {
                    if (!cat.name.trim()) continue;
                    const catName = cat.name.trim();
                    payload[catName] = {};
                    if (cat.icon && cat.icon.trim()) payload[catName].__icon__ = cat.icon.trim();
                    for (const cmd of cat.commands) {
                        if (!cmd.name.trim()) continue;
                        const cmdName = cmd.name.trim();
                        const desc = cmd.desc.trim();
                        const icon = (cmd.icon || '').trim();
                        const prefix = cmd.prefix !== undefined ? (cmd.prefix === ' ' ? '' : cmd.prefix) : undefined;

                        // 构建指令对象
                        if (icon || prefix !== undefined) {
                            const cmdObj = { desc };
                            if (icon) cmdObj.icon = icon;
                            if (prefix !== undefined) cmdObj.prefix = prefix;
                            payload[catName][cmdName] = cmdObj;
                        } else {
                            payload[catName][cmdName] = desc;
                        }
                    }
                }
                const result = await bridge.apiPost('menu', payload);
                if (result && (result.success === true || result.success === 'true')) {
                    showMessage('配置保存成功！');
                    await fetchMenu();
                } else {
                    throw new Error((result && (result.message || result.error)) || '保存响应错误');
                }
            } catch (err) {
                showMessage('保存失败: ' + err.message, 'error');
            } finally {
                saving.value = false;
            }
        };

        onMounted(initBridge);

        return {
            categories,
            saving,
            uploading,
            message,
            pendingDeleteIdx,
            previewIcon,
            resolveIcon,
            uploadIcon,
            addCategory,
            deleteCategory,
            addCommand,
            deleteCommand,
            moveCategory,
            moveCommand,
            saveMenu
        };
    }
}).mount('#app');
