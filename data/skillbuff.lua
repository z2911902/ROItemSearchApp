
	
[2] = {
	temp = GSklv(2)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 1 or temp_wp == 2 then
		WeaponMasteryATK(temp * 4)
	end
}
[3] = {
	temp = GSklv(3)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 3 then
		WeaponMasteryATK(temp * 4)
	end
}

[43] = {
	temp = GSklv(43)
	AddExtParam(1, 107, temp)
}
[55] = {
	temp = GSklv(55)
	temp_2 = GSklv(63)
	temp_3 = GSklv(2007)
	temp_wp = GetWeaponClass(4)
	job = 0
	if temp_wp == 4 or temp_wp == 5 then
		WeaponMasteryATK(temp * 4)
		if temp_2 > 0 and job > 0 then
			WeaponMasteryATK(temp)
		end
		if temp_3 > 0 and job > 0 then
			WeaponMasteryATK(temp)
		end
	end
}

[63] = {
	temp = GSklv(63)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 4 or temp_wp == 5 and temp > 0 then
		PerfectDamage(1)
	end
}

[65] = {
	temp = GSklv(65)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 8 then
		WeaponMasteryATK(temp * 3)
		AddExtParam(1, 52, temp)
	end
}
[105] = {
	temp = GSklv(105)
	if temp == 1 then
		WeaponMasteryATK(4)
		AddExtParam(1, 103, 1)
	end
}
[107] = {
	temp = GSklv(107)
	WeaponMasteryATK(temp * 2)
	AddExtParam(1, 49, temp * 2)
}
[134] = {
	temp = GSklv(134)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 16 then
		WeaponMasteryATK(temp * 3)
	end
}

[226] = {
	temp = GSklv(226)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 2 or temp_wp == 6 then
		WeaponMasteryATK(temp * 3)
	end
}

[248] = {
	temp = GSklv(248)
	AddExtParam(1, 109, temp * 200)
}
[259] = {
	temp = GSklv(259)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 0 or temp_wp == 12 then
		WeaponMasteryATK(temp * 3)
	end
}
[274] = {
	temp = GSklv(274)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 15 then
		WeaponMasteryATK(temp * 10)
	end
}

[284] = {
	temp = GSklv(284)
	AddMdamage_Race(9,temp * 2)
	RaceAddDamage(9, temp * 4)
	if temp == 1 or temp == 2 then
		AddExtParam(1, 106, 1)
	end
	if temp == 3 or temp == 4 then
		AddExtParam(1, 106, 2)
	end
	if temp == 5 then
		AddExtParam(1, 106, 3)
	end

}

[315] = {
	temp = GSklv(315)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 13 or temp_wp == 14 then
		AddExtParam(1, 41, temp * 3)
		AddExtParam(1, 112, temp)
		AddExtParam(1, 167, temp)
	end
}

[2007] = {
	temp = GSklv(2007)
	temp_wp = GetWeaponClass(4)

}
[2248] = {
	temp = GSklv(2248)
	AddExtParam(1, 106, temp)


}
[2276] = {
	temp = GSklv(2276)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 6 or temp_wp == 7 then
		WeaponMasteryATK(temp * 5)
		AddExtParam(1, 49, temp * 3)
	end
}

[2277] = {
	temp = GSklv(2277)
	if target_element == 2 or target_element == 3 then
		WeaponMasteryATK(temp * 10)
	end

}

[2412] = {
	temp = GSklv(2412)
	AddExtParam(1, 110, temp * 30)
}
[2474] = {
	temp = GSklv(2474)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 2 then
		WeaponMasteryATK(temp * 10)
		AddExtParam(1, 49, temp)
	end
}


[5025] = {
	temp = GSklv(5025)
	AddExtParam(1, 106, temp * 20)
	AddExtParam(1, 140, temp * 20)
}
[5031] = {
	temp = GSklv(5031)
	AddRangeAttackDamage(1, temp * 20)
	AddExtParam(1, 50, temp * 20)
	AddExtParam(1, 49, temp * 20)
	AddExtParam(1, 52, temp * 20)
}

[5037] = {
	temp = GSklv(5037)
	AddHealValue(temp * 30)
	AddExtParam(1, 109, temp * 4000)
	AddExtParam(1, 110, temp * 400)

}
[5077] = {
	temp = GSklv(5077)
	AddExtParam(1, 200, temp * 20)
	AddExtParam(1, 109, temp * 400)
	AddExtParam(1, 110, temp * 40)
}

[5228] = {
	temp = GSklv(5228)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 23 then
		AddExtParam(1, 243, temp * 2)
	end
}

[5240] = {
	temp = GSklv(5240)
	if temp > 0 then
		RaceAddDamage(1, 2 + temp)
		RaceAddDamage(6, 2 + temp)
	end
	

}

[5270] = {
	temp = GSklv(5270)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 8 or temp_wp == 15 and temp > 0 then
		AddDamage_Size(1, 0, temp)
		AddDamage_Size(1, 1, temp * 1.45 + 1)
		AddDamage_Size(1, 2, temp * 1.68 + 2)
		if temp == 4 then
			AddDamage_Size(1, 2, 1)
		end
		if temp == 9 then
			SubDamage_Size(1, 2, 1)
		end
	end
}
[5276] = {
	temp = GSklv(5276)	
	AddSkillMDamage(6, temp * 1.5)
}

[5311] = {
	temp = GSklv(5311)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 1 or temp_wp == 11 and temp > 0 then
		AddDamage_Size(1, 0, temp)
		AddDamage_Size(1, 1, temp * 1.45 + 1)
		AddDamage_Size(1, 2, temp * 2)
	end

}
[5312] = {
	temp = GSklv(5312)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 1 or temp_wp == 2 and temp > 0 then
		AddMDamage_Size(1, 0, temp * 1.45 + 1)
		AddMDamage_Size(1, 1, temp * 1.45 + 1)
		AddMDamage_Size(1, 2, temp * 1.45 + 1)
	end
}

[5349] = {
	temp = GSklv(5349)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 13 or temp_wp == 14 then
		AddExtParam(1, 243, temp * 3)
		AddExtParam(1, 242, temp * 3)
	end
}




[5365] = {
	temp = GSklv(5365)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 15 then
		AddSkillMDamage(1, 1)
		AddSkillMDamage(2, 1)
		AddSkillMDamage(3, 1)
		AddSkillMDamage(4, 1)
		AddSkillMDamage(5, 1)
		AddSkillMDamage(1, temp * 1.4)
		AddSkillMDamage(2, temp * 1.4)
		AddSkillMDamage(3, temp * 1.4)
		AddSkillMDamage(4, temp * 1.4)
		AddSkillMDamage(5, temp * 1.4)
	end
}
[5401] = {
	temp = GSklv(5401)
	temp_wp = GetWeaponClass(4)
	if temp_wp == 17 or temp_wp == 18 or temp_wp == 19 or temp_wp == 20 or temp_wp == 21 then
		AddExtParam(1, 242, temp + 2)
	end
}
[5402] = {
	temp = GSklv(5402)
	AddExtParam(1, 238, temp)
}
[5416] = {
	temp = GSklv(5416)
	AddExtParam(1, 243, temp)
}
[5417] = {
	temp = GSklv(5417)
	AddExtParam(1, 237, temp)
}
[5433] = {
	temp = GSklv(5433)
	AddExtParam(1, 242, temp * 1.5)
	AddExtParam(1, 243, temp * 1.5)
}
[5434] = {
	temp = GSklv(5434)
	if temp > 0 then
		UseSkill(5434)
	end
}
[5443] = {
	temp = GSklv(5443)
	if temp > 0 then
		UseSkill(5443)
	end
}
[5450] = {
	temp = GSklv(5450)
	AddExtParam(1, 243, temp)
}
[5464] = {
	temp = GSklv(5464)
	temp_wp = GetWeaponClass(4)
	if temp > 0 and temp_wp == 15 then
		AddExtParam(1, 242, temp + 2)
		AddExtParam(1, 49, temp * 3)
	end
}