Item = {
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
    Stat = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0},
    OnStartEquip = function()
    
    temp = GetRefineLevel(6)
    temp_g = GetEquipGradeLevel(6)
    AddExtParam(1, 111, 15)
    AddExtParam(1, 41, 10*(temp/2))
    AddExtParam(1, 200, 10*(temp/2))
    if temp > 6 then
     SubSpellDelay(10)
    end
    if temp > 8 then
     AddExtParam(1, 242, 3)
     AddExtParam(1, 243, 3)
    end
    if temp > 9 then
     AddExtParam(1, 207, 7)
     AddExtParam(1, 140, 7)
    end
    if temp >10 then
     AddRangeAttackDamage(1, 8)
     AddMeleeAttackDamage(1, 8)
     AddSkillMDamage(10, 8)
    end
    if temp >12 then
     AddRangeAttackDamage(1, 10)
     AddMeleeAttackDamage(1, 10)
     AddSkillMDamage(10, 10)
    end
    
    if temp_g > 0 then
     AddExtParam(1, 242, 10)
     AddExtParam(1, 243, 10)
    end
    if temp_g > 1 then
    RaceAddDamage(9999, 10)
    AddMdamage_Race(9999, 10)
    end
    if temp_g >2 then
    SubSFCTEquipAmount(5000001, 1000, 0)
    end
    if temp_g > 3 and temp > 12 then
    AddDamage_Size(1, 0, 12)
    AddDamage_Size(1, 1, 12)
    AddDamage_Size(1, 2, 12)
    AddMDamage_Size(1, 0, 12)
    AddMDamage_Size(1, 1, 12)
    AddMDamage_Size(1, 2, 12)
    end
    
    end,
    Combiitem = {5000000001, 5000000002, 5000000003, 5000000004, 5000000005, 5000000006, 5000000007, 5000000008, 5000000009, 5000000010, 5000000011},
  },
}
Combiitem = {
  [5000000001] = {
    Item = {5000001, 450293},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 30)
    AddMdamage_Class(1, 30)
    AddDamage_SKID(1, 6521, 30)
    AddDamage_SKID(1, 5334, 30)
    end,
  },
  [5000000002] = {
    Item = {5000001, 450294},
    OnStartEquip = function()
    AddMdamage_Class(1, 10)
    AddDamage_SKID(1, 5220, 30)
    SubSkillDelay(5369, 200)
    end,
  },
  [5000000003] = {
    Item = {5000001, 450295},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 25)
    AddDamage_SKID(1, 6001, 30)
    SubSkillDelay(5256, 5000)
    end,
  },
  [5000000004] = {
    Item = {5000001, 450296},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 20)
    AddDamage_SKID(1, 5287, 30)
    AddDamage_SKID(1, 5322, 30)
    end,
  },
  [5000000005] = {
    Item = {5000001, 450297},
    OnStartEquip = function()
    AddMdamage_Class(1, 35)
    ClassAddDamage(1, 1, 35)
    AddDamage_SKID(1, 6518, 40)
    AddDamage_SKID(1, 5244, 40)
    end,
  },
  [5000000006] = {
    Item = {5000001, 450298},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 10)
    SubSkillDelay(5341, 150)
    SubSkillDelay(5342, 150)
    SubSkillDelay(6004, 150)
    end,
  },
  [5000000007] = {
    Item = {5000001, 450386},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 30)
    AddDamage_SKID(1, 5501, 30)
    AddDamage_SKID(1, 5500, 30)
    end,
  },
  [5000000008] = {
    Item = {5000001, 450387},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 30)
    AddMdamage_Class(1, 30)
    SubSkillDelay(5469, 150)
    SubSkillDelay(5430, 350)
    end,
  },
  [5000000009] = {
    Item = {5000001, 450388},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 20)
    AddMdamage_Class(1, 20)
    AddDamage_SKID(1, 5506, 30)
    AddDamage_SKID(1, 5507, 30)
    end,
  },
  [5000000010] = {
    Item = {5000001, 450389},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 30)
    AddMdamage_Class(1, 30)
    AddDamage_SKID(1, 5488, 30)
    AddDamage_SKID(1, 5490, 30)
    SubSkillDelay(5482, 150)
    end,
  },
  [5000000011] = {
    Item = {5000001, 450391},
    OnStartEquip = function()
    ClassAddDamage(1, 1, 35)
    AddMdamage_Class(1, 35)
    AddDamage_SKID(1, 5460, 30)
    AddDamage_SKID(1, 5454, 30)
    end,
  },
}
