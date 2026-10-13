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
    Combiitem = {},
  },
  [5000001] = {
    Type = "armor",
    Stat = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      local temp_R, temp_G = 0, 0
      temp_R = GetRefineLevel(GetLocation())
      temp_G = GetEquipGradeLevel(GetLocation())
      AddExtParam(0, 41, 12 * math.floor(temp_R / 2))
      AddExtParam(0, 234, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 238, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 111, 2 * math.floor(temp_R / 3))
      AddMeleeAttackDamage(1, 4 * math.floor(temp_R / 4))
      AddRangeAttackDamage(1, 4 * math.floor(temp_R / 4))
      if temp_R >= 9 then
        AddDamage_CRI(1, 15)
      end
      if temp_R >= 11 then
        SubSpellDelay(15)
      end
      if temp_R >= 13 then
        AddDamage_Size(1, 0, 10)
        AddDamage_Size(1, 1, 10)
        AddDamage_Size(1, 2, 10)
      end
    
      AddRaceTolerace(9999, 5)
      AddAttrTolerace(0, 10)
    
      if temp_G >= 1 then
        AddExtParam(0, 45, 200)
        AddExtParam(0, 47, 30)
      end
      if temp_R >= 12 then
        SetIgnoreDefRace_Percent(9999, 15)
      end
      if temp_G >= 2 then
        AddDamage_Property(1, 10, 10)
      end
      if temp_G >= 3 then
        RaceAddDamage(9999, 10)
      end
      if temp_G >= 4 then
        ClassAddDamage(0, 1, 10)
        ClassAddDamage(1, 1, 10)
        ClassAddDamage(2, 1, 10)
      end
    end,
    Combiitem = {2500001, 2500004},
  },
  [5000002] = {
    Type = "armor",
    Stat = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      local temp_R, temp_G = 0, 0
      temp_R = GetRefineLevel(GetLocation())
      temp_G = GetEquipGradeLevel(GetLocation())
      AddExtParam(0, 41, 12 * math.floor(temp_R / 2))
      AddExtParam(0, 234, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 238, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 111, 2 * math.floor(temp_R / 3))
      AddMeleeAttackDamage(1, 4 * math.floor(temp_R / 4))
      AddRangeAttackDamage(1, 4 * math.floor(temp_R / 4))
      if temp_R >= 9 then
        AddDamage_HIT(1, 8)
      end
      if temp_R >= 11 then
        SubSpellDelay(15)
      end
      if temp_R >= 13 then
        AddDamage_Size(1, 0, 10)
        AddDamage_Size(1, 1, 10)
        AddDamage_Size(1, 2, 10)
      end
      AddRaceTolerace(9999, 5)
      AddAttrTolerace(0, 10)
      if temp_G >= 1 then
        AddExtParam(0, 45, 200)
        AddExtParam(0, 47, 30)
      end
      if temp_R >= 12 then
        SetIgnoreDefRace_Percent(9999, 15)
      end
      if temp_G >= 2 then
        AddDamage_Property(1, 10, 10)
      end
      if temp_G >= 3 then
        RaceAddDamage(9999, 10)
      end
      if temp_G >= 4 then
        ClassAddDamage(0, 1, 10)
        ClassAddDamage(1, 1, 10)
        ClassAddDamage(2, 1, 10)
      end
    end,
    Combiitem = {2500005, 2500002},
  },
  [5000003] = {
    Type = "armor",
    Stat = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      local temp_R, temp_G = 0, 0
      temp_R = GetRefineLevel(GetLocation())
      temp_G = GetEquipGradeLevel(GetLocation())
      AddExtParam(0, 200, 12 * math.floor(temp_R / 2))
      AddExtParam(0, 234, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 238, 1 * math.floor(temp_R / 2))
      AddExtParam(0, 111, 2 * math.floor(temp_R / 3))
      AddSkillMDamage(10, 4 * math.floor(temp_R / 4))
      if temp_R >= 9 then
        AddExtParam(0, 140, 8)
      end
      if temp_R >= 11 then
        SubSpellDelay(15)
      end
      if temp_R >= 13 then
        AddMDamage_Size(1, 0, 10)
        AddMDamage_Size(1, 1, 10)
        AddMDamage_Size(1, 2, 10)
      end
      AddRaceTolerace(9999, 5)
      AddAttrTolerace(0, 10)
      if temp_G >= 1 then
        AddExtParam(0, 45, 200)
        AddExtParam(0, 47, 30)
        if temp_R >= 12 then
          SetIgnoreMdefRace(9999, 15)
        end
      end
    
      if temp_G >= 2 then
        AddMDamage_Property(1, 10, 10)
      end
      if temp_G >= 3 then
        AddMdamage_Race(9999, 10)
      end
      if temp_G >= 4 then
        AddMdamage_Class(0, 10)
        AddMdamage_Class(1, 10)
        AddMdamage_Class(2, 10)
      end
    end,
    Combiitem = {2500003, 2500006},
  },
  [5000004] = {
    Type = "armor",
    Stat = {20, 0, 0, 0, 0, 0, 0, 0, 0, 10, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      local temp_R, temp_G = 0, 0
      temp_R = GetRefineLevel(GetLocation())
      temp_G = GetEquipGradeLevel(GetLocation())
      AddExtParam(0, 47, 10)
      AddExtParam(0, 140, 15)
      AddDamage_HIT(1, 15)
      AddDamage_CRI(1, 30)
      AddExtParam(0, 41, 20 * math.floor(temp_R / 4))
      AddExtParam(0, 200, 20 * math.floor(temp_R / 4))
      if temp_R >= 9 then
        SubSpellDelay(8)
      end
      if temp_R >= 13 then
        AddDamage_Property(1, 10, 10)
        AddMDamage_Property(1, 10, 10)
      end
      if temp_G >= 1 then
        AddExtParam(0, 41, 120)
        AddExtParam(0, 200, 120)
      end
      if temp_G >= 2 then
        AddExtParam(0, 244, 80)
        AddExtParam(0, 245, 50)
      end
      if temp_G >= 3 then
        SubSFCTEquipAmount(5000004, 300, 0)
      end
      if temp_G >= 4 then
        AddIgnore_RES_RacePercent(9999, 10)
        AddIgnore_MRES_RacePercent(9999, 10)
      end
    end,
    Combiitem = {2500004, 2500005, 2500006},
  },
  [5000006] = {
    Type = "armor",
    Stat = {20, 0, 0, 0, 0, 0, 0, 0, 0, 20, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
      local temp_R, temp_G = 0, 0
      temp_R = GetRefineLevel(GetLocation())
      temp_G = GetEquipGradeLevel(GetLocation())
      AddExtParam(0, 47, 20)
      AddExtParam(0, 41, 120)
      AddExtParam(0, 140, 12)
      AddMeleeAttackDamage(1, 12)
      AddRangeAttackDamage(1, 12)
      AddSkillMDamage(10, 12)
      AddExtParam(0, 52, 120)
      SubSpellCastTime(10)
      AddGuideAttack(8)
      SubSpellDelay(10)
      AddExtParam(0, 167, 15)
      SetIgnoreDefRace_Percent(9999, 10)
      SetIgnoreMdefRace(9999, 10)
      RaceAddDamage(9999, 6 * math.floor(temp_R / 7))
      AddMdamage_Race(9999, 6 * math.floor(temp_R / 7))
      if temp_R >= 9 then
        AddExtParam(0, 111, 12)
        AddExtParam(0, 112, 12)
      end
      if temp_R >= 13 then
        AddExtParam(0, 242, 8)
        AddExtParam(0, 243, 8)
      end
      if temp_G >= 1 then
        SubSpellDelay(5)
        SetIgnoreDefRace_Percent(9999, 5)
        SetIgnoreMdefRace(9999, 5)
      end
      if temp_G >= 2 then
        SubSFCTEquipAmount(5000006, 200, 0)
      end
      if temp_G >= 3 then
        ClassAddDamage(0, 1, 8)
        ClassAddDamage(1, 1, 8)
        ClassAddDamage(2, 1, 8)
        AddMdamage_Class(0, 8)
        AddMdamage_Class(1, 8)
        AddMdamage_Class(2, 8)
      end
    end
  },
  [9999999999] = {},
}
Combiitem = {
  [2500001] = {
    Item = {5000001, 4174},
    OnStartEquip = function()
      SubAttrTolerace(0, 20)
      AddAttrTolerace(1, 30)
      AddAttrTolerace(2, 30)
      AddAttrTolerace(3, 30)
      AddAttrTolerace(4, 30)
      AddAttrTolerace(5, 30)
      AddAttrTolerace(6, 30)
      AddAttrTolerace(7, 30)
      AddAttrTolerace(8, 30)
      AddAttrTolerace(9, 30)
      AddExtParam(0, 52, 200)
      AddDamage_CRI(1, 50)
    end,
  },
  [2500002] = {
    Item = {5000002, 4174},
    OnStartEquip = function()
      SubAttrTolerace(0, 20)
      AddAttrTolerace(1, 30)
      AddAttrTolerace(2, 30)
      AddAttrTolerace(3, 30)
      AddAttrTolerace(4, 30)
      AddAttrTolerace(5, 30)
      AddAttrTolerace(6, 30)
      AddAttrTolerace(7, 30)
      AddAttrTolerace(8, 30)
      AddAttrTolerace(9, 30)
      AddDamage_HIT(1, 25)
      AddGuideAttack(20)
    end,
  },
  [2500003] = {
    Item = {5000003, 4174},
    OnStartEquip = function()
      SubAttrTolerace(0, 20)
      AddAttrTolerace(1, 30)
      AddAttrTolerace(2, 30)
      AddAttrTolerace(3, 30)
      AddAttrTolerace(4, 30)
      AddAttrTolerace(5, 30)
      AddAttrTolerace(6, 30)
      AddAttrTolerace(7, 30)
      AddAttrTolerace(8, 30)
      AddAttrTolerace(9, 30)
      AddExtParam(0, 140, 25)
      SubSpellCastTime(20)
    end,
  },
  [2500004] = {
    Item = {5000004, 5000001},
    OnStartEquip = function()
      local temp_G = 0
      temp_G = GetEquipGradeLevel(5)
      ClassAddDamage(0, 1, 10)
      ClassAddDamage(1, 1, 10)
      ClassAddDamage(2, 1, 10)
      AddExtParam(0, 234, 1 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 238, 1 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 239, 1 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 242, 2 * math.floor(GetRefineLevel(5) / 3))
      AddExtParam(0, 253, 1 * math.floor(GetRefineLevel(5) / 3))
      if temp_G >= 4 then
        ClassAddDamage(0, 1, 10)
        ClassAddDamage(1, 1, 10)
        ClassAddDamage(2, 1, 10)
      end
    end,
  },
  [2500005] = {
    Item = {5000004, 5000002},
    OnStartEquip = function()
      local temp_G = 0
      temp_G = GetEquipGradeLevel(5)
      ClassAddDamage(0, 1, 10)
      ClassAddDamage(1, 1, 10)
      ClassAddDamage(2, 1, 10)
      AddExtParam(0, 234, 2 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 238, 2 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 242, 3 * math.floor(GetRefineLevel(5) / 3))
      if temp_G >= 4 then
        ClassAddDamage(0, 1, 10)
        ClassAddDamage(1, 1, 10)
        ClassAddDamage(2, 1, 10)
      end
    end,
  },
  [2500006] = {
    Item = {5000004, 5000003},
    OnStartEquip = function()
      local temp_G = 0
      temp_G = GetEquipGradeLevel(5)
      AddMdamage_Class(0, 10)
      AddMdamage_Class(1, 10)
      AddMdamage_Class(2, 10)
      AddExtParam(0, 237, 3 * math.floor(GetRefineLevel(5) / 2))
      AddExtParam(0, 243, 3 * math.floor(GetRefineLevel(5) / 3))
      if temp_G >= 4 then
        AddMdamage_Class(0, 10)
        AddMdamage_Class(1, 10)
        AddMdamage_Class(2, 10)
      end
    end,
  },
}
