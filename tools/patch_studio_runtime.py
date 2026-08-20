"""Patch generated Studio JavaScript for the small UI-only runtime features."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
BUNDLE = ROOT / "studio_ui" / "assets" / "index-B4Zo_uyt.js"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def patch_bundle(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")

    helpers = (
        "function xyueSeedMode(e){let t=String(e||`random`).toLowerCase();return t===`reuse`||t===`fixed`?`fixed`:t===`increase`||t===`decrease`?t:`random`}"
        "function xyueNextSeed(e,t){let n=Number.isFinite(Number(e))?Math.max(0,Math.min(4294967295,Math.floor(Number(e)))):0;return t=xyueSeedMode(t),t===`fixed`?n:t===`increase`?(n+1)%4294967296:t===`decrease`?(n+4294967295)%4294967296:crypto.getRandomValues(new Uint32Array(1))[0]}"
        'function xyueCollisionMode(e){return e==="\u8986\u76d6"||e===`overwrite`?"\u8986\u76d6":e==="\u963b\u6b62"||e===`block`?"\u963b\u6b62":"\u81ea\u52a8\u9012\u589e"}'
        'function xyueStudioMaterialRows(items){let rows=[];for(let item of Array.isArray(items)?items:[]){let kind=String(item?.kind||"");if(!["image","video","audio"].includes(kind))continue;let file=String(item?.file||"");if(!file)continue;let index=rows.filter(row=>row.kind===kind).length+1,prefix=kind==="image"?"\u56fe\u7247":kind==="video"?"\u89c6\u9891":"\u97f3\u9891";rows.push({id:`server-${kind}-${file}`,name:file,alias:`@${prefix}${index}`,kind,meta:`ComfyUI \u7d20\u6750 \u00b7 ${item?.source==="generated"?"\u5df2\u751f\u6210":"input"}`,poster:void 0,active:!1,sourceFile:file})}return rows}'
        'function xyueStudioMaterialOverrides(){return Ft.filter(item=>item.active&&item.sourceFile).map(item=>{let prefix=item.kind==="image"?"\u56fe\u7247":item.kind==="video"?"\u89c6\u9891":"\u97f3\u9891",role=item.kind==="image"?"\u672a\u6307\u5b9a":item.kind==="video"?"\u52a8\u4f5c\u8282\u594f\u6837\u7247":"\u89d2\u8272\u58f0\u7eb9\u951a\u70b9";return{kind:item.kind,file:item.sourceFile,enabled:!0,alias_mode:`@${prefix}N`,role,fit_mode:item.kind==="image"?"\u4fdd\u6301\u539f\u56fe":void 0,start_seconds:0,duration_seconds:0,include_audio:!1,voice_anchor:item.kind==="audio"?`\u58f0\u97f3${item.alias.replace(/^@/,"")}`:void 0,gain_db:0,normalize_peak:!1}})}'
        'function xyueInstallMentionPicker(){let input=document.querySelector(`textarea.prompt-editor`);if(!input||input.__xyueMentionPicker||input.__xyueStandalonePicker)return;input.__xyueStandalonePicker=!0;let menu;const close=()=>{menu?.remove(),menu=void 0},show=()=>{let cursor=input.selectionStart??input.value.length,prefix=input.value.slice(0,cursor),start=Math.max(prefix.lastIndexOf(`@`),prefix.lastIndexOf(`<`));if(start<0)return close();let trigger=prefix[start],query=prefix.slice(start+1);if(/\\n/.test(query)||trigger===`@`&&/\\s/.test(query)||trigger===`<`&&/>/.test(query))return close();let rows=Ft.filter(item=>item.active&&item.sourceFile).filter(item=>`${item.alias} ${item.name}`.toLowerCase().includes(query.toLowerCase()));if(!rows.length)return close();close();let rect=input.getBoundingClientRect();menu=document.createElement(`div`),menu.className=`xyue-mention-picker`;Object.assign(menu.style,{position:`fixed`,zIndex:`30000`,left:`${Math.max(4,rect.left)}px`,top:`${Math.min(window.innerHeight-310,rect.bottom+4)}px`,width:`${rect.width}px`,maxHeight:`300px`,overflowY:`auto`,padding:`5px`,background:`#fff`,border:`1px solid #aeb6bd`,borderRadius:`5px`,boxShadow:`0 10px 24px #1f242833`});rows.forEach(item=>{let row=document.createElement(`button`);row.type=`button`,row.textContent=`${item.alias}  ${item.name}`,Object.assign(row.style,{display:`block`,width:`100%`,padding:`9px`,border:0,textAlign:`left`,background:`transparent`,color:`#252a2f`}),row.onclick=()=>{let current=input.selectionStart??input.value.length,text=input.value.slice(0,current),pos=Math.max(text.lastIndexOf(`@`),text.lastIndexOf(`<`)),index=Ft.filter(other=>other.kind===item.kind&&other.active).indexOf(item)+1,reference=trigger===`@`?item.alias:`<${item.kind[0].toUpperCase()+item.kind.slice(1)} ${index}>`;input.value=input.value.slice(0,pos)+reference+input.value.slice(current),input.dispatchEvent(new Event(`input`,{bubbles:!0})),input.focus(),input.selectionStart=input.selectionEnd=pos+reference.length,close()},menu.append(row)}),document.body.append(menu)};input.addEventListener(`input`,show),input.addEventListener(`click`,show),input.addEventListener(`focus`,show),document.addEventListener(`fullscreenchange`,show),window.addEventListener(`resize`,show),document.addEventListener(`mousedown`,event=>{menu&&!menu.contains(event.target)&&event.target!==input&&close()},{passive:!0})}'
    )
    text = replace_once(text, "function Pe({assets:", helpers + "function Pe({assets:", "runtime helpers")

    seed_start = text.find("(0,A.jsx)(M,{label:`\u91cd\u8bd5\u79cd\u5b50`")
    seed_end = text.find("]}),(0,A.jsxs)(`div`,{className:`sampling-card`", seed_start)
    if seed_start < 0 or seed_end < 0:
        raise RuntimeError("seed input block not found")
    seed_input = "(0,A.jsx)(M,{label:`\\u79cd\\u5b50\\uff08\\u81ea\\u5df1\\u8f93\\u5165 / \\u4e0a\\u6b21\\u7ed3\\u679c\\uff09`,children:(0,A.jsx)(`input`,{className:`seed-input`,type:`number`,min:0,max:4294967295,step:1,value:e.seed||\"\",placeholder:`\\u9996\\u6b21\\u751f\\u6210\\u65f6\\u968f\\u673a`,onChange:t=>r({seed:Math.max(0,Math.min(4294967295,Math.floor(Number(t.target.value)||0)))})})})"
    text = text[:seed_start] + seed_input + text[seed_end:]

    mode_start = text.find("(0,A.jsxs)(`div`,{className:`seed-mode-switch`")
    mode_end = text.find("(0,A.jsx)(M,{label:`调度器`", mode_start)
    if mode_start < 0 or mode_end < 0:
        raise RuntimeError("seed mode block not found")
    mode_block = (
        "(0,A.jsxs)(`div`,{className:`seed-mode-switch`,role:`group`,\"aria-label\":`\\u79cd\\u5b50\\u6a21\\u5f0f`,children:["
        "(0,A.jsx)(`button`,{className:xyueSeedMode(e.seedMode)===`random`?`is-active`:`` ,onClick:()=>r({seedMode:`random`}),children:`\\u968f\\u673a`}),"
        "(0,A.jsx)(`button`,{className:xyueSeedMode(e.seedMode)===`increase`?`is-active`:`` ,onClick:()=>r({seedMode:`increase`}),children:`\\u589e\\u52a0`}),"
        "(0,A.jsx)(`button`,{className:xyueSeedMode(e.seedMode)===`decrease`?`is-active`:`` ,onClick:()=>r({seedMode:`decrease`}),children:`\\u51cf\\u5c11`}),"
        "(0,A.jsx)(`button`,{className:xyueSeedMode(e.seedMode)===`fixed`?`is-active`:`` ,onClick:()=>r({seedMode:`fixed`}),children:`\\u56fa\\u5b9a`})]}),"
    )
    text = text[:mode_start] + mode_block + text[mode_end:]

    text = replace_once(text, "seedMode:e.seedMode===`reuse`?`reuse`:`random`", "seedMode:xyueSeedMode(e.seedMode)", "seed mode normalization")
    text = replace_once(text, "seed:o.seed,model:", "seed:o.seed,seedMode:xyueSeedMode(o.seed_mode||o.seed_control),model:", "import seed mode")
    text = replace_once(text, "seed:e.seed,seed_control:e.seed?`fixed`:`randomize`", "seed:e.seed,seed_mode:xyueSeedMode(e.seedMode),seed_control:xyueSeedMode(e.seedMode)", "export seed mode")
    text = replace_once(text, "let s=Se.seedMode===`reuse`&&Number.isFinite(Se.seed)&&Se.seed>0?Se.seed:crypto.getRandomValues(new Uint32Array(1))[0]", "let s=xyueNextSeed(Se.seed,Se.seedMode)", "run seed resolution")
    text = replace_once(text, "seed_control:`fixed`}", "seed_control:`fixed`,seed_mode:xyueSeedMode(Se.seedMode)}", "resolved seed mode")

    text = replace_once(text, "title:\"\",slate:", "title:`\\u955c\\u5934${String(e).padStart(2,`0`)}`,slate:", "default shot title")
    text = replace_once(text, "var kt={projectName:`\u5f53\u524d\u9879\u76ee`,projectFolder:`\u5f53\u524d\u9879\u76ee`,stagePattern:`{name}_{index:02d}`,finalPattern:`\u007bname\u007d_\u6700\u7ec8`,collision:`increment`", "var kt={projectName:`\u5f53\u524d\u9879\u76ee`,projectFolder:`\u5f53\u524d\u9879\u76ee`,stagePattern:`{name}_{index:02d}`,finalPattern:`\u007bname\u007d_\u6700\u7ec8`,collision:`\\u81ea\\u52a8\\u9012\\u589e`", "default collision")
    text = replace_once(text, "options:[`increment`,`overwrite`,`block`]", "options:[`\\u81ea\\u52a8\\u9012\\u589e`,`\\u8986\\u76d6`,`\\u963b\\u6b62`]", "collision labels")
    text = replace_once(text, "[S,C]=(0,h.useState)({...kt,...qt?.savePolicy||{}})", "[S,C]=(0,h.useState)({...kt,...qt?.savePolicy||{},collision:xyueCollisionMode(qt?.savePolicy?.collision)})", "initial collision")
    text = replace_once(text, "C({...kt,...e.savePolicy||{}})", "C({...kt,...e.savePolicy||{},collision:xyueCollisionMode(e.savePolicy?.collision)})", "session collision")
    text = replace_once(text, "C({...kt,...t.savePolicy||{}})", "C({...kt,...t.savePolicy||{},collision:xyueCollisionMode(t.savePolicy?.collision)})", "project collision")

    text = replace_once(text, "let[n,r]=(0,h.useState)(e),[i,a]", "let[n,r]=(0,h.useState)(e);(0,h.useEffect)(()=>r(e),[e]);let[i,a]", "asset prop refresh")
    text = replace_once(text, "p=e=>{r(t=>t.map(t=>t.id===e?{...t,active:!t.active}:t))}", "p=e=>{r(t=>t.map(t=>t.id===e?{...t,active:!t.active}:t)),Ft=Ft.map(t=>t.id===e?{...t,active:!t.active}:t),window.dispatchEvent(new Event(`xyue-material-change`))}", "asset activation")
    text = replace_once(text, "composition:{enabled:t.enabled,clips:", "material_overrides:xyueStudioMaterialOverrides(),composition:{enabled:t.enabled,clips:", "material payload")
    text = replace_once(text, "[g,we,d,S])", "[g,we,d,S,w])", "material config refresh")

    old_effect = "(0,h.useEffect)(()=>(xt().then(ee).catch(()=>void 0),()=>{o.current?.(),Object.values(l.current).forEach(e=>URL.revokeObjectURL(e)),l.current={}}),[]);"
    new_effect = "(0,h.useEffect)(()=>{let e=!1,notify=()=>ee(e=>({...e}));window.addEventListener(`xyue-material-change`,notify),xt().then(ee).catch(()=>void 0),fetch(`/xyue-h3/materials`,{cache:`no-store`}).then(e=>e.ok?e.json():{materials:[]}).then(t=>{if(e)return;Ft=xyueStudioMaterialRows(t.materials),ee(e=>({...e})),window.setTimeout(()=>xyueInstallMentionPicker(),0)}).catch(()=>void 0),window.setTimeout(()=>xyueInstallMentionPicker(),0);return()=>{e=!0,window.removeEventListener(`xyue-material-change`,notify),o.current?.(),Object.values(l.current).forEach(e=>URL.revokeObjectURL(e)),l.current={}}},[]);"
    text = replace_once(text, old_effect, new_effect, "material library fetch")

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_bundle(BUNDLE)
    print(BUNDLE)
