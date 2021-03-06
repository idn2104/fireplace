from ..utils import *


##
# Hero Powers

# Skitter
class NAX1_04:
	activate = Summon(CONTROLLER, "NAX1_03")

class NAX1h_04:
	activate = Summon(CONTROLLER, "NAX1h_03")


# Rain of Fire
class NAX2_03:
	activate = Hit(RANDOM_ENEMY_MINION, 1) * Count(OPPONENT_HAND)

class NAX2_03H:
	activate = Hit(RANDOM_ENEMY_MINION, 1) * Count(OPPONENT_HAND)


# Web Wrap
class NAX3_02:
	activate = Bounce(RANDOM_ENEMY_MINION)


# Web Wrap
class NAX3_02H:
	activate = Bounce(RANDOM_ENEMY_MINION * 2)


# Raise Dead
class NAX4_04:
	events = Death(ENEMY + MINION).on(Summon(CONTROLLER, "NAX4_03"))

class NAX4_04H:
	events = Death(ENEMY + MINION).on(Summon(CONTROLLER, "NAX4_03H"))


# Necrotic Aura
class NAX6_02:
	activate = Hit(ENEMY_HERO, 3)

class NAX6_02H:
	activate = Hit(ENEMY_HERO, 3)


# Unbalancing Strike
class NAX7_03:
	activate = Hit(TARGET, 3)

class NAX7_03H:
	activate = Hit(TARGET, 4)


# Harvest
class NAX8_02:
	activate = Draw(CONTROLLER)

class NAX8_02H:
	activate = Draw(CONTROLLER), GainMana(CONTROLLER, 1)


# Hateful Strike
class NAX10_03:
	activate = Destroy(TARGET)

class NAX10_03H:
	activate = Destroy(TARGET)


# Decimate
class NAX12_02:
	activate = Buff(ENEMY_MINIONS, "NAX12_02e")

class NAX12_02H:
	activate = Buff(ENEMY_MINIONS, "NAX12_02e")


# Polarity Shift
class NAX13_02:
	activate = Buff(ALL_MINIONS, "NAX13_02e")


# Frost Breath
class NAX14_02:
	activate = Destroy(ENEMY_MINIONS - FROZEN)


# Frost Blast
class NAX15_02:
	activate = Hit(ENEMY_HERO, 2), Freeze(ENEMY_HERO)

class NAX15_02H:
	activate = Hit(ENEMY_HERO, 3), Freeze(ENEMY_HERO)


# Chains
class NAX15_04H:
	activate = Steal(RANDOM_ENEMY_MINION)


##
# Minions

# Deathcharger
class FP1_006:
	deathrattle = Hit(FRIENDLY_HERO, 3)


# Unrelenting Trainee
class NAX8_03:
	deathrattle = Summon(OPPONENT, "NAX8_03t")

# Spectral Trainee
class NAX8_03t:
	events = OWN_TURN_BEGIN.on(Hit(FRIENDLY_HERO, 1))


# Unrelenting Warrior
class NAX8_04:
	deathrattle = Summon(OPPONENT, "NAX8_04t")

# Spectral Warrior
class NAX8_04t:
	events = OWN_TURN_BEGIN.on(Hit(FRIENDLY_HERO, 1))


# Unrelenting Rider
class NAX8_05:
	deathrattle = Summon(OPPONENT, "NAX8_05t")

# Spectral Rider
class NAX8_05t:
	events = OWN_TURN_BEGIN.on(Hit(FRIENDLY_HERO, 1))


# Necroknight
class NAXM_001:
	deathrattle = Destroy(SELF_ADJACENT)


# Skeletal Smith
class NAXM_002:
	deathrattle = Destroy(ENEMY_WEAPON)


##
# Spells

# Locust Swarm
class NAX1_05:
	play = Hit(ENEMY_MINIONS, 3), Heal(FRIENDLY_HERO, 3)


# Necrotic Poison
class NAX3_03:
	play = Destroy(TARGET)


# Plague
class NAX4_05:
	play = Destroy(ALL_MINIONS - ID("NAX4_03") - ID("NAX4_03H"))


# Mindpocalypse
class NAX5_03:
	play = Draw(ALL_PLAYERS) * 2, GainMana(ALL_PLAYERS, 1)


# Deathbloom
class NAX6_03:
	play = Hit(TARGET, 5), Summon(CONTROLLER, "NAX6_03t")

class NAX6_03t:
	deathrattle = Buff(ENEMY_MINIONS, "NAX6_03te")


# Sporeburst
class NAX6_04:
	play = Hit(ENEMY_MINIONS, 1), Summon(CONTROLLER, "NAX6_03t")


# Mark of the Horsemen
class NAX9_07:
	play = Buff(FRIENDLY + (WEAPON | MINION), "NAX9_07e")


# Mutating Injection
class NAX11_04:
	play = Buff(TARGET, "NAX11_04e")


# Enrage
class NAX12_04:
	play = Buff(SELF, "NAX12_04e")


# Polarity Shift
class NAX13_03:
	play = Buff(FRIENDLY_MINIONS, "NAX13_03e")


# Pure Cold
class NAX14_04:
	play = Hit(ENEMY_HERO, 8), Freeze(ENEMY_HERO)


##
# Weapons

# Hook
class NAX10_02:
	deathrattle = Give(CONTROLLER, "NAX10_02")

class NAX10_02H:
	deathrattle = Give(CONTROLLER, "NAX10_02H")


# Jaws
class NAX12_03:
	events = Death(MINION + DEATHRATTLE).on(Buff(SELF, "NAX12_03e"))

class NAX12_03H:
	events = Death(MINION + DEATHRATTLE).on(Buff(SELF, "NAX12_03e"))
