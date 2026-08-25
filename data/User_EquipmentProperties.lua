Item = {
  [13200] = {
    Type = "ammo",
    Stat = {0, 25},
    Combiitem = {},
  },
  [410211] = {
    Type = "armor",
    Stat = {2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      temp = get(11)
      AddExtParam(0, 41, temp)
      AddExtParam(0, 200, temp)
    end,
    Combiitem = {2000004910, 2000004913},
  },
  [18000] = {
    Type = "Cannonball",
    Stat = {0, 100},
    Combiitem = {},
  },
  [18001] = {
    Type = "Cannonball",
    Stat = {6, 120},
  },
  [18002] = {
    Type = "Cannonball",
    Stat = {7, 120},
  },
  [18003] = {
    Type = "Cannonball",
    Stat = {8, 120},
  },
  [18004] = {
    Type = "Cannonball",
    Stat = {0, 250},
  },
  [18005] = {
    Type = "Cannonball",
    Stat = {1, 120},
  },
  [18006] = {
    Type = "Cannonball",
    Stat = {4, 120},
  },
  [18007] = {
    Type = "Cannonball",
    Stat = {2, 120},
  },
  [18008] = {
    Type = "Cannonball",
    Stat = {3, 120},
  },
  [18009] = {
    Type = "Cannonball",
    Stat = {5, 120},
  },
  [5000001] = {
    Type = "armor",
    Stat = {0, 5, 5, 5, 5, 5, 5, 0, 0, 0, 2, 3, 3, 3, 3, 3, 3},
    OnStartEquip = function()
    end,
    Combiitem = {5000000001, 5000000002, 5000000003, 5000000004, 5000000005, 5000000006},
  },
  [5000002] = {
    Type = "armor",
    Stat = {0, 5, 5, 5, 5, 5, 5, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
    end,
    Combiitem = {5000000011, 5000000012, 5000000013, 5000000014, 5000000015, 5000000016, 5000000031, 5000000017, 5000000018, 5000000019, 5000000020, 5000000021},
  },
  [5000003] = {
    Type = "armor",
    Stat = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
    AddExtParam(1, 242, 3)
    AddExtParam(1, 243, 3)
    end,
    Combiitem = {5000000022, 5000000023, 5000000024, 5000000025, 5000000026, 5000000032, 5000000027, 5000000028, 5000000029, 5000000030},
  },
}
Combiitem = {
  [5000000001] = {
    Item = {5000001, 450440},
    OnStartEquip = function()
    AddExtParam(1, 41, 200)
    SetIgnoreDefRace_Percent(0, 10)
    SetIgnoreDefRace_Percent(1, 10)
    SetIgnoreDefRace_Percent(2, 10)
    SetIgnoreDefRace_Percent(3, 10)
    SetIgnoreDefRace_Percent(4, 10)
    SetIgnoreDefRace_Percent(5, 10)
    SetIgnoreDefRace_Percent(6, 10)
    SetIgnoreDefRace_Percent(7, 10)
    SetIgnoreDefRace_Percent(8, 10)
    SetIgnoreDefRace_Percent(9, 10)
    
    end,
  },
  [5000000002] = {
    Item = {5000001, 450441},
    OnStartEquip = function()
    AddExtParam(1, 200, 200)
    SetIgnoreMdefRace(0, 10)
    SetIgnoreMdefRace(1, 10)
    SetIgnoreMdefRace(2, 10)
    SetIgnoreMdefRace(3, 10)
    SetIgnoreMdefRace(4, 10)
    SetIgnoreMdefRace(5, 10)
    SetIgnoreMdefRace(6, 10)
    SetIgnoreMdefRace(7, 10)
    SetIgnoreMdefRace(8, 10)
    SetIgnoreMdefRace(9, 10)
    
    end,
  },
  [5000000003] = {
    Item = {5000001, 470333},
    OnStartEquip = function()
    AddDamage_Size(1,0, 15)
    AddDamage_Size(1,1, 15)
    AddDamage_Size(1,2, 15)
    SubSpellDelay(8)
    AddExtParam(1, 167, 15)
    SetIgnoreDefRace_Percent(0, 7)
    SetIgnoreDefRace_Percent(1, 7)
    SetIgnoreDefRace_Percent(2, 7)
    SetIgnoreDefRace_Percent(3, 7)
    SetIgnoreDefRace_Percent(4, 7)
    SetIgnoreDefRace_Percent(5, 7)
    SetIgnoreDefRace_Percent(6, 7)
    SetIgnoreDefRace_Percent(7, 7)
    SetIgnoreDefRace_Percent(8, 7)
    SetIgnoreDefRace_Percent(9, 7)
    
    end,
  },
  [5000000004] = {
    Item = {5000001, 470334},
    OnStartEquip = function()
    AddMDamage_Size(1, 0, 15)
    AddMDamage_Size(1, 1, 15)
    AddMDamage_Size(1, 2, 15)
    SubSpellDelay(8)
    SubSpellCastTime(15)
    SetIgnoreMdefRace(0, 7)
    SetIgnoreMdefRace(1, 7)
    SetIgnoreMdefRace(2, 7)
    SetIgnoreMdefRace(3, 7)
    SetIgnoreMdefRace(4, 7)
    SetIgnoreMdefRace(5, 7)
    SetIgnoreMdefRace(6, 7)
    SetIgnoreMdefRace(7, 7)
    SetIgnoreMdefRace(8, 7)
    SetIgnoreMdefRace(9, 7)
    
    
    end,
  },
  [5000000005] = {
    Item = {5000001, 480545},
    OnStartEquip = function()
    AddRangeAttackDamage(1, 15)
    AddMeleeAttackDamage(1, 15)
    SetIgnoreDefRace_Percent(0, 8)
    SetIgnoreDefRace_Percent(1, 8)
    SetIgnoreDefRace_Percent(2, 8)
    SetIgnoreDefRace_Percent(3, 8)
    SetIgnoreDefRace_Percent(4, 8)
    SetIgnoreDefRace_Percent(5, 8)
    SetIgnoreDefRace_Percent(6, 8)
    SetIgnoreDefRace_Percent(7, 8)
    SetIgnoreDefRace_Percent(8, 8)
    SetIgnoreDefRace_Percent(9, 8)
    end,
  },
  [5000000006] = {
    Item = {5000001, 480546},
    OnStartEquip = function()
    AddSkillMDamage(10, 15)
    SetIgnoreMdefRace(0, 8)
    SetIgnoreMdefRace(1, 8)
    SetIgnoreMdefRace(2, 8)
    SetIgnoreMdefRace(3, 8)
    SetIgnoreMdefRace(4, 8)
    SetIgnoreMdefRace(5, 8)
    SetIgnoreMdefRace(6, 8)
    SetIgnoreMdefRace(7, 8)
    SetIgnoreMdefRace(8, 8)
    SetIgnoreMdefRace(9, 8)
    
    end,
  },
  [5000000011] = {
    Item = {5000002, 300636},
    OnStartEquip = function()
    AddDamage_Property(1, 10, 5)
    end,
  },
  [5000000012] = {
    Item = {5000002, 300642},
    OnStartEquip = function()
    AddDamage_Property(1, 10, 5)
    end,
  },
  [5000000013] = {
    Item = {5000002, 300639},
    OnStartEquip = function()
    AddMDamage_Property(1,10, 5)
    end,
  },
  [5000000014] = {
    Item = {5000002, 300657},
    OnStartEquip = function()
    AddMDamage_Property(1,10, 5)
    end,
  },
  [5000000015] = {
    Item = {5000002, 300633},
    OnStartEquip = function()
    SubDamage_Size(0, 0, 30)
    SubDamage_Size(0, 1, 30)
    SubDamage_Size(0, 2, 30)
    SubMDamage_Size(0, 0, 30)
    SubMDamage_Size(0, 1, 30)
    SubMDamage_Size(0, 2, 30)
    AddExtParam(1, 45, 50)
    AddExtParam(1, 47, 15)
    AddExtParam(1, 244, 20)
    AddExtParam(1, 245, 10)
    end,
  },
  [5000000016] = {
    Item = {5000002, 300646},
    OnStartEquip = function()
    AddDamage_Size(1, 0,15)
    AddDamage_Size(1, 1,15)
    AddDamage_Size(1, 2,15)
    AddExtParam(1, 234, 5)
    AddExtParam(1, 41, 30)
    end,
  },
  [5000000017] = {
    Item = {5000002, 300635},
    OnStartEquip = function()
    AddExtParam(1, 111, 45)
    SubExtParam(1, 207, 15)
    SubExtParam(1, 140, 15)
    end,
  },
  [5000000018] = {
    Item = {5000002, 300644},
    OnStartEquip = function()
    ClassAddDamage(0, 1, 8)
    ClassAddDamage(1, 1, 8)
    AddExtParam(1, 242, 10)
    
    end,
  },
  [5000000019] = {
    Item = {5000002, 300637},
    OnStartEquip = function()
    ClassAddDamage(0, 1, 8)
    ClassAddDamage(1, 1, 8)
    AddExtParam(1, 242, 10)
    
    end,
  },
  [5000000020] = {
    Item = {5000002, 300641},
    OnStartEquip = function()
    AddMdamage_Class(0, 8)
    AddMdamage_Class(1, 8)
    AddExtParam(1, 243, 10)
    AddExtParam(1, 140, 5)
    
    end,
  },
  [5000000021] = {
    Item = {5000002, 300643},
    OnStartEquip = function()
    AddMdamage_Class(0, 8)
    AddMdamage_Class(1, 8)
    AddExtParam(1, 243, 10)
    AddExtParam(1, 140, 5)
    
    end,
  },
  [5000000022] = {
    Item = {5000003, 300640},
    OnStartEquip = function()
    AddExtParam(1, 52, 200)
    AddExtParam(1, 253, 7)
    AddDamage_CRI(1, 10)
    
    end,
  },
  [5000000023] = {
    Item = {5000003, 300638},
    OnStartEquip = function()
    AddDamage_HIT(1, 8)
    AddExtParam(1, 111, 5)
    AddRangeAttackDamage(1, 8)
    AddMeleeAttackDamage(1, 8)
    SubSpellCastTime(5)
    
    end,
  },
  [5000000024] = {
    Item = {5000003, 300655},
    OnStartEquip = function()
    AddMdamage_Race(9999, 15)
    AddExtParam(1, 140, 10)
    SubSpellCastTime(5)
    end,
  },
  [5000000025] = {
    Item = {5000003, 300649},
    OnStartEquip = function()
    AddSkillMDamage(10, 20)
    SubSpellCastTime(5)
    SubSpellDelay(3)
    AddExtParam(1, 167, 7)
    
    end,
  },
  [5000000026] = {
    Item = {5000003, 300650},
    OnStartEquip = function()
    AddRangeAttackDamage(1, 8)
    AddMeleeAttackDamage(1, 8)
    AddExtParam(1, 52, 80)
    AddGuideAttack(10)
    SubSpellCastTime(5)
    end,
  },
  [5000000027] = {
    Item = {5000003, 300652},
    OnStartEquip = function()
    AddSkillMDamage(10, 20)
    SubSpellCastTime(5)
    SubSpellDelay(3)
    AddExtParam(1, 167, 7)
    
    end,
  },
  [5000000028] = {
    Item = {5000003, 300653},
    OnStartEquip = function()
    AddRangeAttackDamage(1, 8)
    AddMeleeAttackDamage(1, 8)
    AddExtParam(1, 52, 80)
    AddGuideAttack(10)
    SubSpellCastTime(5)
    end,
  },
  [5000000029] = {
    Item = {5000003, 300654},
    OnStartEquip = function()
    AddRangeAttackDamage(1, 8)
    AddMeleeAttackDamage(1, 8)
    AddExtParam(1, 52, 80)
    AddGuideAttack(10)
    SubSpellCastTime(5)
    end,
  },
  [5000000030] = {
    Item = {5000003, 5000002},
    OnStartEquip = function()
    AddExtParam(1, 41, 45)
    AddExtParam(1, 200, 45)
    AddIgnore_RES_RacePercent(9999, 10)
    AddIgnore_MRES_RacePercent(9999, 10)
    end,
  },
  [5000000031] = {
    Item = {5000002, 300645},
    OnStartEquip = function()
    AddMDamage_Size(1, 0, 15)
    AddMDamage_Size(1, 1, 15)
    AddMDamage_Size(1, 2, 15)
    AddExtParam(1, 237, 5)
    end,
  },
  [5000000032] = {
    Item = {5000003, 300651},
    OnStartEquip = function()
    AddRangeAttackDamage(1, 8)
    AddMeleeAttackDamage(1, 8)
    AddExtParam(1, 52, 80)
    AddGuideAttack(10)
    SubSpellCastTime(5)
    end,
  },
}
