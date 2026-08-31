# 額外參數對照表 buff規則10開頭狀態ID，20開頭技能ID，30開頭隱藏ID(例如超初無死亡獎勵)
all_skill_entries = {#範例[    "": {"buff":"","type": "技能/料理","code":["",""]},    
    #紅呆來源https://forum.gamer.com.tw/C.php?bsn=4212&snA=439331
    "掉寶呆(本次)0818-0901": {"buff":"1597","type": "料理","code":["RaceSubDamage(9999, 70)","SubDamage_Property(1, 10, 70)","ClassSubDamage(0, 1, 70)","ClassSubDamage(1, 1, 70)","SubMdamage_Race(9999, 70)","SubMDamage_Property(1, 10, 70)","SubMdamage_Class(0, 70)","SubMdamage_Class(1, 70)","SubExtParam(1, 41, 300)","SubExtParam(1, 200, 300)","SubDamage_Size(1, 0, 70)","SubDamage_Size(1, 1, 70)","SubDamage_Size(1, 2, 70)","SubMDamage_Size(1, 0, 70)","SubMDamage_Size(1, 1, 70)","SubMDamage_Size(1, 2, 70)"],"exclusive": "itemsugar"},
    "掉寶呆(上次)0616-0701": {"buff":"1597","type": "料理","code":["RaceSubDamage(9999, 70)","SubDamage_Property(1, 10, 70)","ClassSubDamage(0, 1, 70)","ClassSubDamage(1, 1, 70)","SubMdamage_Race(9999, 70)","SubMDamage_Property(1, 10, 70)","SubMdamage_Class(0, 70)","SubMdamage_Class(1, 70)","SubSkillMDamage(10, 30)","SubMeleeAttackDamage(1, 30)","SubRangeAttackDamage(1, 30)","SubExtParam(1, 47, 200)"],"exclusive": "itemsugar"},
    #"掉寶呆(上次)0506-0519": {"buff":"1597","type": "料理","code":["RaceSubDamage(9999, 70)","SubDamage_Property(1, 10, 70)","ClassSubDamage(0, 1, 70)","ClassSubDamage(1, 1, 70)","SubMdamage_Race(9999, 70)","SubMDamage_Property(1, 10, 70)","SubMdamage_Class(0, 70)","SubMdamage_Class(1, 70)","SubExtParam(1, 52, 300)","SubExtParam(1, 207, 30)","SubExtParam(1, 140, 30)"],"exclusive": "itemsugar"},
    #"掉寶呆(上次)0317-0331": {"buff":"1597","type": "料理","code":["SubMDamage_Size(1, 0, 70)","SubMDamage_Size(1, 1, 70)","SubMDamage_Size(1, 2, 70)","SubMDamage_Property(1, 10, 70)","SubMdamage_Race(9999, 70)","SubMdamage_Class(0, 70)","SubMdamage_Class(1, 70)","AddSpellCastTime(30)","SubDamage_Size(1, 0, 70)","SubDamage_Size(1, 1, 70)","SubDamage_Size(1, 2, 70)","SubDamage_Property(1, 10, 70)","RaceAddDamage(9999, 70)","ClassSubDamage(0, 1, 70)","ClassSubDamage(1, 1,70)"],"exclusive": "itemsugar"},
    "波利蛋糕": {"buff":"1480","type": "料理","code":["AddExtParam(1, 103, 15)","AddExtParam(1, 104, 15)","AddExtParam(1, 105, 15)","AddExtParam(1, 106, 15)","AddExtParam(1, 107, 15)","AddExtParam(1, 108, 15)","AddExtParam(1, 234, 15)","AddExtParam(1, 235, 15)","AddExtParam(1, 236, 15)","AddExtParam(1, 237, 15)","AddExtParam(1, 238, 15)","AddExtParam(1, 239, 15)","AddDamage_Property(1, 10, 12)","AddMDamage_Property(1, 10, 12)"]},
    #10料
    "力量料理": {"buff":"241","type": "料理","code":["AddExtParam(0,103,10)"],"exclusive": "food_str"},
    "敏捷料理": {"buff":"242","type": "料理","code":["AddExtParam(0,104,10)"],"exclusive": "food_agi"},
    "體力料理": {"buff":"243","type": "料理","code":["AddExtParam(0,105,10)"],"exclusive": "food_vit"},
    "智慧料理": {"buff":"244","type": "料理","code":["AddExtParam(0,106,10)"],"exclusive": "food_int"},
    "靈巧料理": {"buff":"245","type": "料理","code":["AddExtParam(0,107,10)"],"exclusive": "food_dex"},
    "幸運料理": {"buff":"246","type": "料理","code":["AddExtParam(0,108,10)"],"exclusive": "food_luk"},
    "終極料理": {"buff":"1034","type": "料理","code":["AddExtParam(1, 41, 30)","AddExtParam(1, 200, 30)"],"exclusive": "atkmatk30"},
    "萬能年糕": {"buff":"685","type": "料理","code":["AddExtParam(1, 41, 30)","AddExtParam(1, 200, 30)"],"exclusive": "atkmatk30"},
    #1641=10料6總總和
    "活力激發劑": {"buff":"1641","type": "料理","code":["AddExtParam(0,103,20)","AddExtParam(0,104,20)","AddExtParam(0,105,20)","AddExtParam(0,106,20)","AddExtParam(0,107,20)","AddExtParam(0,108,20)"],"exclusive": "food_str,food_agi,food_vit,food_int,food_dex,food_luk"},
    #15料
    "力量棒棒條": {"buff":"271","type": "料理","code":["AddExtParam(0,103,15)"],"exclusive": "food_str"},
    "敏捷棒棒條": {"buff":"272","type": "料理","code":["AddExtParam(0,104,15)"],"exclusive": "food_agi"},
    "體力棒棒條": {"buff":"273","type": "料理","code":["AddExtParam(0,105,15)"],"exclusive": "food_vit"},
    "智慧棒棒條": {"buff":"274","type": "料理","code":["AddExtParam(0,106,15)"],"exclusive": "food_int"}, 
    "靈巧棒棒條": {"buff":"275","type": "料理","code":["AddExtParam(0,107,15)"],"exclusive": "food_dex"},
    "幸運棒棒條": {"buff":"276","type": "料理","code":["AddExtParam(0,108,15)"],"exclusive": "food_luk"},
    "特性增強藥劑": {"buff":"1509","type": "料理","code":["AddExtParam(1, 234, 5)","AddExtParam(1, 235, 5)","AddExtParam(1, 236, 5)","AddExtParam(1, 238, 5)","AddExtParam(1, 237, 5)","AddExtParam(1, 239, 5)","AddExtParam(1, 242, 10)","AddExtParam(1, 243, 10)"]},
    #20料    
    "烤野豬": {"buff":"491","type": "料理","code":["AddExtParam(0,103,20)"]},
    "捕蟲藥草煎": {"buff":"495","type": "料理","code":["AddExtParam(0,104,20)"]},
    "米洛斯燒肉": {"buff":"493","type": "料理","code":["AddExtParam(0,105,20)"]},
    "狼血雞尾酒": {"buff":"492","type": "料理","code":["AddExtParam(0,106,20)"]},
    "小雪獸冰茶": {"buff":"494","type": "料理","code":["AddExtParam(0,107,20)"]},
    "畢帝特龍尾麵": {"buff":"496","type": "料理","code":["AddExtParam(0,108,20)"]},
    #
    "力量防護卷軸": {"buff":"996","type": "料理","code":["AddExtParam(1, 45, 500)","AddExtParam(1, 47, 200)"]},
    
    #活動---------
    #櫻花, 春花季
    "蒙布朗蛋糕": {"buff":"1469","type": "料理","code":["AddMDamage_Size(1, 0, 10)","AddMDamage_Size(1, 1, 10)","AddMDamage_Size(1, 2, 10)","AddDamage_Size(1, 0, 10)","AddDamage_Size(1, 1, 10)","AddDamage_Size(1, 2, 10)"]},
    "櫻花年糕": {"buff":"1470","type": "料理","code":["AddMDamage_Property(1, 10, 10)","AddDamage_Property(1, 10, 10)"]},
    "甜甜可麗餅": {"buff":"1471","type": "料理","code":["AddExtParam(1, 111, 10)","AddExtParam(1, 112, 10)"]},
    "豐滿花樹枝": {"buff":"1472","type": "料理","code":["AddSkillMDamage(10, 10)","AddRangeAttackDamage(1, 10)","AddMeleeAttackDamage(1, 10)"]},
    #海洋週
    "夏季韓式宴會麵": {"buff":"1473","type": "料理","code":["AddMDamage_Property(1, 10, 10)","AddDamage_Property(1, 10, 10)"]},
    "香料烤魷魚": {"buff":"1474","type": "料理","code":["AddMDamage_Size(1, 0, 10)","AddMDamage_Size(1, 1, 10)","AddMDamage_Size(1, 2, 10)","AddDamage_Size(1, 0, 10)","AddDamage_Size(1, 1, 10)","AddDamage_Size(1, 2, 10)"]},
    "甜甜西瓜布丁": {"buff":"1475","type": "料理","code":["AddMeleeAttackDamage(1, 10)","AddRangeAttackDamage(1, 10)","AddSkillMDamage(10, 10)"]},
    "冰涼西瓜汁": {"buff":"1476","type": "料理","code":["AddExtParam(1, 207, 15)","AddExtParam(1, 140, 15)"]},
    "冰涼紅豆剉冰": {"buff":"1477","type": "料理","code":["AddExtParam(1, 111, 10)","AddExtParam(1, 112, 10)"]},
    "鹹奶油爆米花": {"buff":"1478","type": "料理","code":["SubSpellCastTime(10)","AddExtParam(1, 54, 2)"]},
    #學術節料理
    "學術節米餅": {"buff":"1485","type": "料理","code":["AddMDamage_Size(1, 0, 10)","AddMDamage_Size(1, 1, 10)","AddMDamage_Size(1, 2, 10)","AddDamage_Size(1, 0, 10)","AddDamage_Size(1, 1, 10)","AddDamage_Size(1, 2, 10)","AddExtParam(1, 239, 15)"]},
    "學術節餅乾": {"buff":"1486","type": "料理","code":["AddMeleeAttackDamage(1, 12)","AddRangeAttackDamage(1,  12)","AddSkillMDamage(10, 12)","AddExtParam(1, 50, 30)"]},
    "學術節即溶咖啡": {"buff":"1487","type": "料理","code":["AddExtParam(1, 207, 15)","AddExtParam(1, 140, 15)","SubSpellCastTime(10)"]},
    "祕密文件": {"buff":"1454","type": "料理","code":["AddExtParam(1, 49, 0)","AddMDamage_Property(1, 10, 10)","AddDamage_Property(1, 10, 10)"]},
    #冬季狩獵
    "肉量加倍三明治": {"buff":"1489","type": "料理","code":["AddMDamage_Size(1, 0, 15)","AddMDamage_Size(1, 1, 15)","AddMDamage_Size(1, 2, 15)","AddMDamage_Property(1, 10, 10)","AddDamage_Size(1, 0, 15)","AddDamage_Size(1, 1, 15)","AddDamage_Size(1, 2, 15)","AddDamage_Property(1, 10, 10)"]},
    "暖胃香料紅酒": {"buff":"1490","type": "料理","code":["AddExtParam(1, 207, 10)","AddExtParam(1, 140, 10)","AddMeleeAttackDamage(1, 10)","AddRangeAttackDamage(1, 10)","AddSkillMDamage(10, 10)"]},
    "暖心蛋酒": {"buff":"1491","type": "料理","code":["AddExtParam(1, 111, 10)","AddExtParam(1, 112, 10)","SubSpellCastTime(10)"]},
    #活動---------

    #攻速水
    "集中藥水": {"buff":"37","type": "料理","code":["AddExtParam(1, 301, 10)"],"exclusive": "ASPD_1"},
    "覺醒藥水": {"buff":"38","type": "料理","code":["AddExtParam(1, 301, 15)"],"exclusive": "ASPD_1"},
    "菠色克藥水": {"buff":"39","type": "料理","code":["AddExtParam(1, 301, 20)"],"exclusive": "ASPD_1"},
    "毒藥瓶": {"buff":"10391","type": "料理","code":["AddExtParam(1, 301, 20)"]},

    "高級戰鬥藥": {"buff":"663","type": "料理","code":["ClassAddDamage(0, 1, 10)","ClassAddDamage(1, 1, 10)","AddExtParam(1, 140, 10)","SubExtParam(1, 111, 5)","SubExtParam(1, 112, 5)"]},
    "揮擊藥水": {"buff":"487","type": "料理","code":["AddExtParam(1, 41, 50)"]},
    "魔力藥水": {"buff":"487","type": "料理","code":["AddExtParam(1, 200, 50)"]},
    "紅色藥草活化液": {"buff":"1170","type": "料理","code":["AddMeleeAttackDamage(1, 15)","AddRangeAttackDamage(1, 15)"]},
    "藍色藥草活化液": {"buff":"1171","type": "料理","code":["AddSkillMDamage(10, 15)"]},
    "戰神蒂爾之祝福": {"buff":"796","type": "料理","code":["AddExtParam(1, 41, 20)","AddExtParam(1, 200, 20)"]},#遊戲內不會顯示atk
    "魔幻香水": {"buff":"867","type": "料理","code":["AddExtParam(1, 41, 30)","AddExtParam(1, 200, 30)","AddExtParam(1, 207, 1)","AddExtParam(1, 140, 1)","AddExtParam(1, 54, 1)","AddExtParam(1, 49, 30)","AddExtParam(1, 50, 30)"]},
    "極限藥水": {"buff":"1065","type": "料理","code":["AddExtParam(1, 111, 5)","AddExtParam(1, 112, 5)","AddRangeAttackDamage(1, 5)","AddDamage_CRI(1, 5)","AddSkillMDamage(10, 5)"]},
    "研磨劑": {"buff":"295","type": "料理","code":["AddExtParam(1, 52, 30)"]},
    "紅色狂暴藥水": {"buff":"664","type": "料理","code":["AddExtParam(1, 41, 30)","AddExtParam(1, 200, 30)","AddExtParam(1, 167, 5)","SubSpellCastTime(5)","SubExtParam(1, 111, 10)","SubExtParam(1, 112, 10)"]},
    #變身
    "變身卷軸(幽靈弓箭手/森林妖精)": {"buff":"","type": "料理","code":["AddRangeAttackDamage(1, 25)"],"exclusive": "Transformation"},
    "變身卷軸(蓋俄斯提/犬妖弓箭手)": {"buff":"","type": "料理","code":["AddRangeAttackDamage(1, 30)"],"exclusive": "Transformation"},
    "變身卷軸(馬爾杜克/惡耗女妖)": {"buff":"","type": "料理","code":["AddExtParam(1, 200, 25)"],"exclusive": "Transformation"},
    "變身卷軸(行妖術者/風魔巫師)": {"buff":"","type": "料理","code":["AddExtParam(1, 200, 50)"],"exclusive": "Transformation"},



    #====技能
    #騎領
    "怒爆": {"buff":"131","id": "RK","type": "技能","code":["UseSkill(7)"]},
    "天龍光環": {"buff":"1176","id": "RK","type": "技能","code":["UseSkill(5210)","temp = GetSkillLevel(5210)","AddDamage_SKID(1, 2008, temp * 10)","AddDamage_SKID(1, 5004, temp * 10)"]},
    "盧恩石1": {"buff":"318","id": "RK","type": "技能","code":["AddExtParam(1, 103, 30)","AddMeleeAttackDamage(1, 30)"]},
    "盧恩石5": {"buff":"322","id": "RK","type": "技能","code":["temp = GetSkillLevel(2010)","AddExtParam(0,302,temp / 10 * 4)","AddExtParam(1, 41, temp * 7)"]},
    "盧恩石10": {"buff":"1154","id": "RK","type": "技能","code":["AddExtParam(1, 111, 30)","AddExtParam(1, 112, 30)","AddDamage_Size(1, 0, 30)","AddDamage_Size(1, 1, 30)","AddDamage_Size(1, 2, 30)","AddDamage_CRI(1, 30)","AddMeleeAttackDamage(1, 30)","AddRangeAttackDamage(1, 30)"]},
    "集中攻擊": {"buff":"105","id": "RK","type": "技能","code":["temp = GetSkillLevel(357)","AddExtParam(1, 207, (temp * 2) + 5)"]},
    "靈氣劍": {"buff":"103","id": "RK","type": "技能","code":["UseSkill(355)"]},

    #皇家
    "盾咒LV3": {"buff":"1316","id": "RG","type": "技能","code":["AddExtParam(1, 41, 150)","AddExtParam(1, 200, 150)"]},
    "靈感": {"buff":"407","id": "RG","type": "技能","code":["UseSkill(2325)","temp = GetSkillLevel(2325)","AddExtParam(1, 49, 12 * temp)","AddExtParam(1, 103, 6 * temp)","AddExtParam(1, 104, 6 * temp)","AddExtParam(1, 105, 6 * temp)","AddExtParam(1, 106, 6 * temp)","AddExtParam(1, 107, 6 * temp)","AddExtParam(1, 108, 6 * temp)","AddExtParam(1, 111, 4 * temp)","AddExtParam(1, 41, 40 * temp)","AddExtParam(1, 200, 40 * temp)"]},
    "抗性聖盾": {"buff":"1220","id": "RG","type": "技能","code":["UseSkill(5262)","temp = GetSkillLevel(5262)","AddSkillMDamage(6, temp * 3)"]},
    "末日審判": {"buff":"1222","id": "RG","type": "技能","code":["UseSkill(5263)"]},
    "攻擊架式": {"buff":"1203","id": "RG","type": "技能","code":["temp = GetSkillLevel(5260)","AddExtParam(1, 242, temp * 3)","AddExtParam(1, 243, temp * 3)","SubExtParam(1, 45, temp * 40)"],"exclusive": "Frame"},
    "防禦架式": {"buff":"1202","id": "RG","type": "技能","code":["UseSkill(5255)","temp = GetSkillLevel(5255)","AddExtParam(1, 45, 50 + (temp * 50))","SubExtParam(1, 41, temp * 50)"],"exclusive": "Frame"},
    #主教 加速天賜跟四轉慈悲百合id相同，改動加速天賜的id。
    "神威祈福": {"buff":"15","id": "AB","type": "技能","code":["AddExtParam(1, 200, 25)","Kamui_SpecialATK(25)"]},
    "慈悲術": {"buff":"10","id": "AB","type": "技能","code": ["temp = 70 / 10","AddExtParam(0,103,10 + math.floor(temp))","AddExtParam(0,106,10 + math.floor(temp)","AddExtParam(0,107,10 + math.floor(temp)","AddExtParam(0,49,20)"]},
    "天使之賜福": {"buff":"10010","id": ["AB","SN","SU"],"type": "技能","code": ["AddExtParam(0,103,10)","AddExtParam(0,106,10)","AddExtParam(0,107,10)","AddExtParam(0,49,20)"]},
    "純白百合花": {"buff":"12","id": "AB","type": "技能","code":["temp = 70 / 10","AddExtParam(0,104,12 + math.floor(temp))","AddExtParam(0,167,10 + math.floor(temp))"]},
    "加速術": {"buff":"10012","id":  ["AB","SN","SU"],"type": "技能","code":["AddExtParam(0,104,12)","AddExtParam(0,167,10)"]},
    "天使之障壁": {"buff":"9","id":  ["AB","SN","SU"],"type": "技能","code":["AddExtParam(1, 109, 500)"]},
    "神聖權能": {"buff":"1201","id": "AB","type": "技能","code":["AddExtParam(1, 242, 50)","AddExtParam(1, 243, 50)"]},
    "全心奉獻": {"buff":"1227","id": "AB","type": "技能","code":["AddExtParam(1, 235, 10)","AddExtParam(1, 236, 10)","AddExtParam(1, 237, 10)"],"exclusive": "STA.WIS.SPL"},
    "祝福讚歌": {"buff":"1228","id": "AB","type": "技能","code":["AddExtParam(1, 234, 10)","AddExtParam(1, 238, 10)","AddExtParam(1, 239, 10)"],"exclusive": "POW.CON.CRT"},
    "神聖防護": {"buff":"1199","id": "AB","type": "技能","code":["AddIgnore_RES_RacePercent(9999, 25)"]},
    "光耀天命": {"buff":"1198","id": "AB","type": "技能","code":["AddIgnore_MRES_RacePercent(9999, 25)"]},
    "爆裂聖光": {"buff":"1200","id": "AB","type": "技能","code":["AddExtParam(1, 253, 10)"]},
    "贖罪": {"buff":"340","id": "AB","type": "技能","code":["SetIgnoreDefRace_Percent(9999, 25)","SetIgnoreMdefRace(9999, 25)"]},
    #聖裁
    "點穴-球": {"buff":"425","id": "SU","type": "技能","code":["UseSkill(2346)","AddDamage_SKID(1, 273, 50)","AddDamage_SKID(1, 372, 50)","AddDamage_SKID(1, 371, 50)"]},
    "點穴-反": {"buff":"426","id": "SU","type": "技能","code":["UseSkill(2347)","temp = GetSkillLevel(2347)","temp_AGI = total_AGI","AddExtParam(1, 41, temp * 8)","AddExtParam(1, 207, temp)","AddExtParam(1, 167, (temp_AGI * temp) / 60)","AddDamage_SKID(1, 2332, 30)","AddDamage_SKID(1, 2336, 30)"],"exclusive": "GENTLETOUCH"},
    "點穴-活": {"buff":"427","id": "SU","type": "技能","code":["UseSkill(2348)","temp = GetSkillLevel(2348)","AddExtParam(1, 45, temp*2)","AddExtParam(1, 111, temp*2)","AddDamage_SKID(1, 2330, 30)","AddDamage_SKID(1, 2343, 30)"],"exclusive": "GENTLETOUCH"},
    "堅毅信念": {"buff":"1160","id": "SU","type": "技能","code":["UseSkill(5238)","temp = GetSkillLevel(5238)","AddExtParam(1, 41, 5 + temp * 5)","AddExtParam(1, 242, 5 + temp * 2)"],"exclusive": "FAITH"},
    "堅定信念": {"buff":"1162","id": "SU","type": "技能","code":["UseSkill(5239)","temp = GetSkillLevel(5239)","AddExtParam(1, 111, 2 * temp)"],"exclusive": "FAITH"},
    "真誠信念": {"buff":"1161","id": "SU","type": "技能","code":["UseSkill(5242)","temp = GetSkillLevel(5242)","AddGuideAttack(4 * temp)","AddExtParam(1, 54, temp)"],"exclusive": "FAITH"},
    "焰魔散彈": {"buff":"1326","id": "SU","type": "技能","code":["UseSkill(5243)"]},
    #斬首
    "致命塗毒": {"buff":"114","id": "GX","type": "技能","code":["UseSkill(378)"]},
    "強效毒液": {"buff":"1194","id": "GX","type": "技能","code":["AddIgnore_RES_RacePercent(9999, 20)"]},
    "魅影強化": {"buff":"192","id": "GX","type": "技能","code":["UseSkill(5285)"]},
    "偽裝強化": {"buff":"333","id": "GX","type": "技能","code":["UseSkill(2033)"]},
    "劇毒武器": {"buff":"341","id": "GX","type": "技能","code":["AddMeleeAttackDamage(1, 10)"]},
    "劇毒武器:熱病": {"buff":"103411","id": "GX","type": "技能","code":["AddDamage_CRI(1, 15)"]},
    "劇毒武器:狂笑": {"buff":"103412","id": "GX","type": "技能","code":["SubSpellDelay(10)"]},
    
    #704
    "五行符": {"buff":"1359","id": "SL","type": "技能","code":["AddMDamage_Property(1, 0, 20)","AddMDamage_Property(1, 1, 20)","AddMDamage_Property(1,2, 20)","AddMDamage_Property(1, 3, 20)","AddMDamage_Property(1, 4, 20)","AddDamage_Property(1, 0, 20)","AddDamage_Property(1, 1, 20)","AddDamage_Property(1,2, 20)","AddDamage_Property(1, 3, 20)","AddDamage_Property(1, 4, 20)"]},
    "武士符": {"buff":"1357","id": "SL","type": "技能","code":["AddExtParam(1, 242, 10)"]},
    "隼鷹靈魂": {"buff":"1058","id": "SL","type": "技能","code":["AddExtParam(1, 41, 50)"]},
    "法師符": {"buff":"1358","id": "SL","type": "技能","code":["AddExtParam(1, 243, 10)"]},
    "精靈靈魂": {"buff":"1057","id": "SL","type": "技能","code":["AddExtParam(1, 200, 50)"]},
    "天地神靈": {"buff":"1365","id": "SL","type": "技能","code":["AddMeleeAttackDamage(1, 25)","AddRangeAttackDamage(1, 25)","AddSkillMDamage(10, 25)"]},
    "四方五行的保佑": {"buff":"1364","id": "SL","type": "技能","code":["UseSkill(5431)","AddExtParam(1, 243, 25)"]},
    #風鷹
    "心神凝聚": {"buff":"3","id": ["RA","SN"],"type": "技能","code":["temp = 2 + GetSkillLevel(45)","tempAGI = skill_focus_AGI","tempDEX = skill_focus_DEX","AddExtParam(1, 104, tempAGI * temp/100)","AddExtParam(1, 107, tempDEX * temp/100)"]},
    #agi跟dex只吃角色基本素質+job加成+裝備基礎(不含精煉給的)+被動技能常駐，
    #料理、卡片、附魔、詞條類、攻擊觸發、非常駐的技能都不算。
    "狙殺瞄準": {"buff":"115","id": "RA","type": "技能","code":["UseSkill(380)","AddExtParam(1, 52, 100)","AddExtParam(1, 49, 30)","AddExtParam(1, 103, 5)","AddExtParam(1, 104, 5)","AddExtParam(1, 105, 5)","AddExtParam(1, 106, 5)","AddExtParam(1, 107, 5)","AddExtParam(1, 108, 5)"]},
    "精英狙擊": {"buff":"722","id": "RA","type": "技能","code":["AddRangeAttackDamage(1, 350)"],"exclusive": "sniper_group"},
    "憤怒暴風": {"buff":"1252","id": "RA","type": "技能","code":["UseSkill(5328)","AddRangeAttackDamage(1, 350)","AddDamage_SKID(1, 5334, 20)"],"exclusive": "sniper_group"},
    #詩人
    "布萊奇之詩": {"buff":"72","id": "MI","type": "技能","code":["SubSpellDelay(30)"]},
    "朝風車突擊": {"buff":"442","id": "MI","type": "技能","code":["AddExtParam(1, 41, 20 + 2 * 10)"]},
    "伊登的蘋果": {"buff":"73","id": "MI","type": "技能","code":["AddExtParam(1, 111, 20)"]},

    #舞娘
    "女神之吻": {"buff":"76","id": "WA","type": "技能","code":["AddExtParam(1, 52, 1 * 10)","AddDamage_CRI(1, 2 * 10)"]},
    "月光小夜曲": {"buff":"447","id": "WA","type": "技能","code":["AddExtParam(1, 200, 20 + 2 * 10)"]},
    "搖擺舞": {"buff":"429","id": "WA","type": "技能","code":["AddExtParam(1, 167, 25)"]},

    #詩人舞娘
    "神秘交響曲": {"buff":"1256","id": ["MI","WA",],"type": "技能","code":["UseSkill(5351)","AddDamage_SKID(1, 5355, 100)","AddDamage_SKID(1, 5353, 100)","AddDamage_SKID(1, 5357, 100)","AddMdamage_Race(7, 50)","AddMdamage_Race(5, 50)","RaceAddDamage(7, 50)","RaceAddDamage(5, 50)"]},
    "戰鼓震天": {"buff":"80","id": ["MI","WA",],"type": "技能","code":["AddExtParam(1, 41, 40)"]},
    "豐年頌": {"buff":"715","id": ["MI","WA",],"type": "技能","code":["AddExtParam(1, 111, 25)"]},
    "雷拉多露水": {"buff":"451","id": ["MI","WA",],"type": "技能","code":["AddExtParam(1, 111, 20)"]},
    "無限哼唱聲": {"buff":"454","id": ["MI","WA",],"type": "技能","code":["AddSkillMDamage(10, 20)"]},
    "與狼共舞": {"buff":"441","id": ["MI","WA",],"type": "技能","code":["AddRangeAttackDamage(1, 5)","AddExtParam(1, 167, 25)"]},
    "普隆德拉進行曲": {"buff":"1263","id": ["MI","WA",],"type": "技能","code":["AddExtParam(1, 242, 22)"]},
    "暮色小夜曲": {"buff":"1262","id": ["MI","WA",],"type": "技能","code":["AddExtParam(1, 243, 22)"]},
    
    
    
    #魅影
    "追跡狀態": {"buff":"","id": "SC","type": "技能","code":["UseSkill(5315)","UseSkill(6513)","UseSkill(6514)","UseSkill(5316)"]},
    "靠近狀態": {"buff":"","id": "SC","type": "技能","code":["UseSkill(5321)"]},
    "深淵殺手": {"buff":"1245","id": "SC","type": "技能","code":["temp = GetSkillLevel(5318)","AddExtParam(1, 242, temp * 2 + 10)","AddExtParam(1, 243, temp * 2 + 10)","AddExtParam(1, 49, temp * 20 + 100)"]},
    "自動魅影念咒": {"buff":"393","id": "SC","type": "技能","code":["temp = GetSkillLevel(2286)","AddExtParam(1, 200, temp * 5)"]},
    #妖術
    #"魔力拳": {"buff":"432","id": "SO","type": "技能","code":["UseSkill(2445)","temp = GetSkillLevel(14)","temp1 = GetSkillLevel(19)","temp2 = GetSkillLevel(20)","temp3 = GetSkillLevel(2445)","AddDamage_passive_SKID(1, 14, -100+(100*temp)+(20*temp3))","AddDamage_passive_SKID(1, 19, -100+(100*temp1)+(20*temp3))","AddDamage_passive_SKID(1, 20, -100+(100*temp2)+(20*temp3))"]},
    "精靈控制Lv.1": {"buff":"","id": "SO","type": "技能","code":["UseSkill(2456)","if GUSklv(5375) == 1 then","temp1 = GetSkillLevel(19)","AddDamage_passive_SKID(1, 19, -100+(100*temp1))","end","if GUSklv(5376) == 1 then","temp = GetSkillLevel(14)","AddDamage_passive_SKID(1, 14, -100+(100*temp))","end","if GUSklv(5377) == 1 then","temp2 = GetSkillLevel(20)","AddDamage_passive_SKID(1, 20, -100+(100*temp2))","end"]},
    "召喚元素:阿爾多雷 火": {"buff":"","id": "SO","type": "技能","code":["UseSkill(5375)","AddDamage_SKID(1, 5372, 30)","AddSkillMDamage(3, 10)"],"exclusive": "4ht_elves"},
    "召喚元素:迪盧比奧 水": {"buff":"","id": "SO","type": "技能","code":["UseSkill(5376)","AddDamage_SKID(1, 5369, 30)","AddSkillMDamage(1, 10)"],"exclusive": "4ht_elves"},
    "召喚元素:普羅賽拉 風": {"buff":"","id": "SO","type": "技能","code":["UseSkill(5377)","AddDamage_SKID(1, 5370, 30)","AddSkillMDamage(4, 10)"],"exclusive": "4ht_elves"},
    "召喚元素:泰雷莫圖斯 地": {"buff":"","id": "SO","type": "技能","code":["UseSkill(5378)","AddDamage_SKID(1, 5373, 30)","AddSkillMDamage(2, 10)"],"exclusive": "4ht_elves"},
    "召喚元素:普羅賽拉 毒": {"buff":"","id": "SO","type": "技能","code":["AddDamage_SKID(1, 5371, 30)","AddSkillMDamage(5, 10)"],"exclusive": "4ht_elves"},
    "火屬性領域": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(3, 20)"]},
    "水屬性領域": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(1, 20)"]},
    "風屬性領域": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(4, 20)"]},
    "火之紋章LV3": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(4, 25)","AddExtParam(1, 200, 50)"]},
    "風之紋章LV3": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(4, 25)"]},
    "水之紋章LV3": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(4, 25)"]},
    "地之紋章LV3": {"buff":"","id": "SO","type": "技能","code":["AddSkillMDamage(4, 25)"]},
    "咒力賦予": {"buff":"1271","id": "SO","type": "技能","code":["AddExtParam(1, 243, 20)"]},
    "打擊強化": {"buff":"445","id": "SO","type": "技能","code":["AddExtParam(1, 41, 100)","AddGuideAttack(70)"]},
    #基因
    "大聲吶喊": {"buff":"30","id": ["GE","ME"],"type": "技能","code":["AddExtParam(1, 103, 4)","AddExtParam(1, 41, 30)"]},
    "手推車加速": {"buff":"118","id": "GE","type": "技能","code":["WeaponMasteryATK(50)"]},
    "研究報告": {"buff":"1248","id": "GE","type": "技能","code":["UseSkill(5347)"]},
    #機匠
    #大聲吶喊跟基因重複
    "凶砍": {"buff":"25","id": "ME","type": "技能","code":["AddExtParam(1, 207, 25)"],"exclusive": "BOVERTHRUST"},
    "凶砍(隊友)": {"buff":"10025","id": "ME","type": "技能","code":["AddExtParam(1, 207, 15)"],"exclusive": "BOVERTHRUST"},
    "凶砍最大值": {"buff":"188","id": "ME","type": "技能","code":["AddExtParam(1, 207, 100)"],"exclusive": "BOVERTHRUST"},
    "速度激發": {"buff":"23","id": "ME","type": "技能","code":["temp_wp = GetWeaponClass(4)","if temp_wp == 6 or temp_wp == 7 or temp_wp == 8 or temp_wp == 15 then","AddExtParam(1, 301, 30)","end"]},
    "無視體型攻擊": {"buff":"24","id": "ME","type": "技能","code":["PerfectDamage(1)"]},
    "武器值最大化": {"buff":"26","id": "ME","type": "技能","code":["UseSkill(114)"]},
    "戰斧踏滅狀態": {"buff":"1235","id": "ME","type": "技能","code":["UseSkill(5295)"]},
    "騎乘魔導機甲": {"buff":"","id": "ME","type": "技能","code":["temp = GetSkillLevel(2255)","WeaponMasteryATK(temp * 15)"]},
    
    
    #禁咒
    "終極念力": {"buff":"717","id": "WL","type": "技能","code":["SubSpellCastTime(50)","AddDamage_passive_SKID(1, 13, 200)","AddDamage_passive_SKID(1, 11, 200)","AddDamage_passive_SKID(1, 400, 200)","AddDamage_passive_SKID(1, 2202, 200)","AddDamage_passive_SKID(1, 2201, 200)","AddDamage_passive_SKID(1, 5220, 200)"]},
    "魔力增幅": {"buff":"113","id": "WL","type": "技能","code":["UseSkill(366)"]},
    "魔力巔峰Lv1(水晶波爆)": {"buff":"1184","id": "WL","type": "技能","code":["UseSkill(5232)","AddExtParam(1, 45, 300)","AddExtParam(1, 47, 100)","addattrtolerace(1, 30)","AddSkillMDamage(1, 30)"]},
    "魔力巔峰Lv3": {"buff":"1152","id": "WL","type": "技能","code":["UseSkill(5232)","AddDamage_SKID(1, 5222, 300)","AddDamage_SKID(1, 5218, 200)","AddDamage_SKID(1, 5215, 150)"],"exclusive": "CLIMAX"},
    "魔力巔峰Lv4(毀滅颶風)": {"buff":"1151","id": "WL","type": "技能","code":["UseSkill(5232)","AddSkillMDamage(4, 30)","AddExtParam(1, 200, 100)"]},
    "魔法省悟": {"buff":"355","id": "WL","type": "技能","code":["UseSkill(2206)"]},
    
    #終初
    #心神凝聚跟風鷹重複
    #天賜與主教重複
    #加速跟主教重複
    "突破極限": {"buff":"1383","id": "SN","type": "技能","code":["UseSkill(5461)"]},
    "突破規矩": {"buff":"1384","id": "SN","type": "技能","code":["UseSkill(5462)"]},
    "征服危機": {"buff":"1671","id": "SN","type": "技能","code":["temp = GetSkillLevel(5505)","AddExtParam(1, 109, temp * 15000)","AddExtParam(1, 243, temp * 3)","AddExtParam(1, 242, temp * 3)"]},
    "無死亡獎勵": {"buff":"3043071","id": "SN","type": "技能","code":["AddExtParam(1, 103, 10)","AddExtParam(1, 104, 10)","AddExtParam(1, 105, 10)","AddExtParam(1, 107, 10)","AddExtParam(1, 106, 10)","AddExtParam(1, 108, 10)"]},
    
    
    #忍者
    "四色符": {"buff": ["1667","1668","1669","1670"],"id": ["OB","KO"],"type": "技能","code":["UseSkill(5499)"]},
    "噩夢狀態": {"buff":"","id": ["OB","KO"],"type": "技能","code":["UseSkill(5493)","UseSkill(5494)","UseSkill(5495)"]},
    "暗器狀態": {"buff":"","id": ["OB","KO"],"type": "技能","code":["UseSkill(5484)"]},
    #槍手
    "王牌出手": {"buff":"","id": "RE","type": "技能","code":["temp = GetSkillLevel(5414)","UseSkill(5414)","AddRangeAttackDamage(1, temp * 10)","AddExtParam(1, 242, temp * 3)"]},
    "專注瞄準": {"buff":"1345","id": "RE","type": "技能","code":["AddExtParam(1, 41, 150)","AddExtParam(1, 49, 250)","AddExtParam(1, 239, 30)"]},
    "格林狂熱": {"buff":"204","id": "RE","type": "技能","code":["temp = GetSkillLevel(517)","AddExtParam(1, 41, temp * 10 + 20)"]},    
    "瘋狂凱斯樂": {"buff":"203","id": "RE","type": "技能","code":["AddExtParam(1, 41, 100)"],"exclusive": "ALTER_MADNESSCANCEL"},
    "白金祭壇": {"buff":"758","id": "RE","type": "技能","code":["temp = GetSkillLevel(2563)","AddExtParam(1, 41, temp * 10 + 100)"],"exclusive": "ALTER_MADNESSCANCEL"},
    #魂鈴師
    "蝦群": {"buff":"920","id": "SUM","type": "技能","code":["UseSkill(5040)","AddExtParam(1, 207, 10)","AddExtParam(1, 140, 10)"]},
    "捲甲蟲暴衝": {"buff":"918","id": "SUM","type": "技能","code":["UseSkill(5035)","AddExtParam(1, 104, 40)","AddRangeAttackDamage(1, 10)"]},
    "喵喵/喵喵不休": {"buff":"953","id": "SUM","type": "技能","code":["UseSkill(5055)","AddExtParam(1, 41, 100)","AddExtParam(1, 200, 100)"]},
    "急速交流": {"buff":"1377","id": "SUM","type": "技能","code":["UseSkill(5447)","temp = GetSkillLevel(5447)","AddExtParam(1, 242, temp * 3)","AddExtParam(1, 243, temp * 3)","AddExtParam(1, 254, temp * 3)"]},
    "神龜沙雕節": {"buff":"1368","id": "SUM","type": "技能","code":["AddExtParam(1, 235, 10)","AddExtParam(1, 236, 10)","AddExtParam(1, 237, 10)"],"exclusive": "STA.WIS.SPL"},
    "神龜海洋慶典": {"buff":"1367","id": "SUM","type": "技能","code":["AddExtParam(1, 234, 10)","AddExtParam(1, 238, 10)","AddExtParam(1, 239, 10)"],"exclusive": "POW.CON.CRT"},
    "玄鹿五色角": {"buff":"1376","id": "SUM","type": "技能","code":["UseSkill(5444)","temp = GetSkillLevel(5443)","AddDamage_SKID(1, 5028, temp * 50)"]},
    "靈物祝福": {"buff":"1378","id": "SUM","type": "技能","code":["UseSkill(5448)","AddExtParam(1, 242, 50)","AddExtParam(1, 243, 50)"]},
    
    # 天帝
    "溫暖的風": {"buff":"474","id": "SE","type": "技能","code":["UseSkill(425)"],},
    "太陽英姿": {"buff":"1040","id": "SE","type": "技能","code":["temp = GetSkillLevel(2591)","AddExtParam(1, 207, 2 + temp)"],"exclusive": "posture"},
    "月亮英姿": {"buff":"1038","id": "SE","type": "技能","code":["temp = GetSkillLevel(2575)","AddExtParam(1, 109, 2 + temp)"],"exclusive": "posture"},
    "星星英姿": {"buff":"1043","id": "SE","type": "技能","code":["temp = GetSkillLevel(2578)","AddExtParam(1, 167, 4 + (temp * 2))"],"exclusive": "posture"},
    "宇宙英姿": {"buff":"1039","id": "SE","type": "技能","code":["temp = GetSkillLevel(2583)","AddExtParam(1, 103, 2 + temp)","AddExtParam(1, 104, 2 + temp)","AddExtParam(1, 105, 2 + temp)","AddExtParam(1, 106, 2 + temp)","AddExtParam(1, 107, 2 + temp)","AddExtParam(1, 108, 2 + temp)"],"exclusive": "posture"},
    
    "太陽光輝": {"buff":"1036","id": "SE","type": "技能","code":["temp = GetSkillLevel(2590)","AddDamage_SKID(1, 2592, temp * 5)"],"exclusive": "Glory"},
    "月亮光輝": {"buff":"1035","id": "SE","type": "技能","code":["temp = GetSkillLevel(2574)","AddDamage_SKID(1, 2576, temp * 5)"],"exclusive": "Glory"},
    "星星光輝": {"buff":"1037","id": "SE","type": "技能","code":["temp = GetSkillLevel(2577)","AddDamage_SKID(1, 2584, temp * 5)"],"exclusive": "Glory"},

    "天氣正午": {"buff":"1386","id": "SE","type": "技能","code":["UseSkill(5465)"],"exclusive": "ENCHANTING_SKY"},
    "天氣午夜": {"buff":"1389","id": "SE","type": "技能","code":["UseSkill(5468)"],"exclusive": "ENCHANTING_SKY"},
    "天機合一": {"buff":"1392","id": "SE","type": "技能","code":["UseSkill(5465)","UseSkill(5468)"],"exclusive": "ENCHANTING_SKY"},
    "太陽和月亮和星星的融合": {"buff":"20444","id": "SE","type": "技能","code":["UseSkill(444)"],},
    "太陽和月亮和星星的奇蹟/憎惡": {"buff":"160","id": "SE","type": "技能","code":["UseSkill(434)"],},
    
}   
