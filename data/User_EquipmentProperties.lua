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
}
Combiitem = {
}
